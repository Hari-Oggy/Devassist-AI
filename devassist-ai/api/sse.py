"""
Server-Sent Events (SSE) Manager — DevAssist-AI Phase 5.

Replaces the existing polling-based frontend update system with a
real-time push model. The frontend opens a single persistent HTTP
connection and receives streamed events as review progress happens.

Architecture:
    SSEManager (singleton)
        ├── EventBus — broadcast queue per review_id
        └── Client registry — tracks connected StreamingResponse clients

Wire format (each event is flushed to the client):
    data: {"type": "review_started", "review_id": 42, "message": "..."}\n\n

FastAPI route (in api/routes/events.py) calls:
    await manager.subscribe(review_id) → AsyncGenerator
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from core.logger import get_logger

logger = get_logger("api.sse")


# ── SSE event formatter ────────────────────────────────────────────────

def format_sse_event(
    data: dict[str, Any],
    event: str | None = None,
    retry_ms: int | None = None,
) -> str:
    """Serialize a dict to SSE wire format.

    SSE format::

        event: review_started       ← optional named event type
        data: {"review_id": 42}     ← JSON payload
        retry: 3000                 ← optional reconnect delay ms
                                    ← blank line terminates event

    Args:
        data: JSON-serializable payload dict.
        event: Optional named event type string.
        retry_ms: Optional reconnect delay hint for the browser.

    Returns:
        Properly formatted SSE string including trailing ``\\n\\n``.
    """
    lines: list[str] = []
    if event:
        lines.append(f"event: {event}")
    if retry_ms is not None:
        lines.append(f"retry: {retry_ms}")
    lines.append(f"data: {json.dumps(data, default=str)}")
    lines.append("")   # blank line terminates the event
    lines.append("")
    return "\n".join(lines)


def _make_event(
    event_type: str,
    review_id: int,
    message: str = "",
    extra: dict | None = None,
) -> dict:
    """Build a standard event payload dict."""
    payload = {
        "type": event_type,
        "review_id": review_id,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    return payload


# ── SSE Manager ────────────────────────────────────────────────────────

class SSEManager:
    """Central hub for broadcasting review progress events to SSE clients.

    Each review gets its own asyncio.Queue. When an event is published,
    it is put onto every queue subscribed to that review_id.

    Usage::

        # In the review worker:
        await sse_manager.publish(
            review_id=42,
            event_type="finding_added",
            message="SQL injection risk found in auth.py:42",
            extra={"severity": "error", "file": "auth.py", "line": 42},
        )

        # In the FastAPI SSE route (yields to StreamingResponse):
        async for chunk in sse_manager.subscribe(review_id=42):
            yield chunk
    """

    def __init__(self, max_queue_size: int = 100) -> None:
        # review_id → list of asyncio.Queue (one per connected client)
        self._queues: dict[int, list[asyncio.Queue]] = {}
        self._max_queue_size = max_queue_size
        self._lock = asyncio.Lock()

    # ── Publish ────────────────────────────────────────────────────────

    async def publish(
        self,
        review_id: int,
        event_type: str,
        message: str = "",
        extra: dict | None = None,
    ) -> int:
        """Broadcast an event to all clients subscribed to a review.

        Args:
            review_id: The review being updated.
            event_type: Event name (e.g. 'review_started', 'finding_added').
            message: Human-readable description.
            extra: Optional extra key-value data to include in the payload.

        Returns:
            Number of clients that received the event.
        """
        payload = _make_event(event_type, review_id, message, extra)
        sse_bytes = format_sse_event(payload, event=event_type)

        async with self._lock:
            queues = self._queues.get(review_id, [])

        sent = 0
        for q in queues:
            try:
                q.put_nowait(sse_bytes)
                sent += 1
            except asyncio.QueueFull:
                logger.warning(
                    "SSE queue full for review_id=%d — dropping event %s",
                    review_id, event_type,
                )

        logger.debug(
            "SSE publish: review_id=%d type=%s clients=%d",
            review_id, event_type, sent,
        )
        return sent

    async def publish_review_started(self, review_id: int, mode: str = "fast") -> None:
        await self.publish(
            review_id, "review_started",
            message=f"Review started in {mode} mode",
            extra={"mode": mode},
        )

    async def publish_review_completed(
        self, review_id: int, findings_count: int, duration_seconds: float
    ) -> None:
        await self.publish(
            review_id, "review_completed",
            message=f"Review complete: {findings_count} findings in {duration_seconds:.1f}s",
            extra={"findings_count": findings_count, "duration_seconds": duration_seconds},
        )

    async def publish_review_failed(self, review_id: int, error: str) -> None:
        await self.publish(
            review_id, "review_failed",
            message=f"Review failed: {error}",
            extra={"error": error},
        )

    async def publish_finding(
        self,
        review_id: int,
        file_path: str,
        line: int,
        severity: str,
        message: str,
    ) -> None:
        await self.publish(
            review_id, "finding_added",
            message=message,
            extra={"file": file_path, "line": line, "severity": severity},
        )

    # ── Subscribe ─────────────────────────────────────────────────────

    async def subscribe(
        self,
        review_id: int,
        timeout_seconds: float = 300.0,
    ) -> AsyncGenerator[str, None]:
        """Async generator that yields SSE-formatted strings for a review.

        Intended to be used directly in a FastAPI ``StreamingResponse``.

        Args:
            review_id: Which review to subscribe to.
            timeout_seconds: Max time to wait for events before auto-closing.

        Yields:
            SSE-formatted strings to stream to the client.

        Example::

            @router.get("/events/{review_id}")
            async def stream_review_events(review_id: int):
                return StreamingResponse(
                    sse_manager.subscribe(review_id),
                    media_type="text/event-stream",
                )
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)

        async with self._lock:
            if review_id not in self._queues:
                self._queues[review_id] = []
            self._queues[review_id].append(queue)

        logger.info("SSE client subscribed: review_id=%d", review_id)

        # Send an initial heartbeat so the browser doesn't time out
        yield format_sse_event(
            _make_event("connected", review_id, "SSE stream connected"),
            event="connected",
        )

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        queue.get(), timeout=timeout_seconds
                    )
                    yield chunk
                    # Check for terminal events
                    if '"review_completed"' in chunk or '"review_failed"' in chunk:
                        break
                except asyncio.TimeoutError:
                    # Send keepalive comment line so connection stays open
                    yield ": keepalive\n\n"
        finally:
            async with self._lock:
                queues = self._queues.get(review_id, [])
                if queue in queues:
                    queues.remove(queue)
                if not queues and review_id in self._queues:
                    del self._queues[review_id]
            logger.info("SSE client disconnected: review_id=%d", review_id)

    # ── Introspection ──────────────────────────────────────────────────

    @property
    def active_subscriptions(self) -> dict[int, int]:
        """Return {review_id: client_count} for all active subscriptions."""
        return {rid: len(qs) for rid, qs in self._queues.items() if qs}

    @property
    def total_clients(self) -> int:
        """Return total number of connected SSE clients."""
        return sum(len(qs) for qs in self._queues.values())


# ── Singleton ──────────────────────────────────────────────────────────

sse_manager: SSEManager = SSEManager()
