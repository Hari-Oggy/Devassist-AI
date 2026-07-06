"""
Server-Sent Events (SSE) Manager — Redis Pub/Sub Edition.

Architecture (fixed cross-process bug):
    Worker process  → redis.publish("sse:events", event_json)
    FastAPI process → redis.subscribe("sse:events") → yield to SSE clients

The original implementation used in-memory asyncio.Queue which only works
when worker and API run in the SAME process. Celery runs in a DIFFERENT
process so events were silently dropped and the frontend never received them.

Wire format (each event is flushed to the client):
    data: {"type": "review_started", "review_id": 42, "message": "..."}\\n\\n

FastAPI route (in api/routes/events.py) calls:
    async for chunk in sse_manager.subscribe(review_id) → AsyncGenerator
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timezone
from typing import Any, AsyncGenerator


from core.logger import get_logger

logger = get_logger("api.sse")

# Redis channel name for all SSE events
_SSE_CHANNEL = "devassist:sse:events"


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


# ── Redis helpers ──────────────────────────────────────────────────────

_redis_client = None
_redis_checked = False
_redis_lock = threading.Lock()


def _get_redis():
    """Lazy Redis client. Cached after first attempt. Thread-safe."""
    global _redis_client, _redis_checked
    with _redis_lock:
        if _redis_checked:
            return _redis_client
        _redis_checked = True
        try:
            import redis as _redis
            from core.config import get_settings
            settings = get_settings()
            r = _redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                health_check_interval=30,
            )
            r.ping()
            _redis_client = r
            logger.info("SSE: Redis Pub/Sub connection established")
        except Exception as e:
            _redis_client = None
            logger.warning(
                f"SSE: Redis unavailable ({e}). "
                "Falling back to in-process queue (SSE events won't cross process boundary)."
            )
        return _redis_client


# ── SSE Manager ────────────────────────────────────────────────────────

class SSEManager:
    """Central hub for broadcasting review progress events to SSE clients.

    Uses Redis Pub/Sub when available so that Celery workers (separate OS
    process) can publish events that reach FastAPI SSE clients.

    Falls back to in-process asyncio.Queue when Redis is unavailable
    (e.g., in unit tests). In that fallback mode cross-process delivery
    won't work, but single-process usage still works correctly.

    Publishing (from any process):
        await sse_manager.publish(review_id, "review_started", ...)

    Subscribing (FastAPI SSE route):
        async for chunk in sse_manager.subscribe(review_id):
            yield chunk
    """

    def __init__(self, max_queue_size: int = 200) -> None:
        # Fallback in-process queues keyed by review_id
        self._queues: dict[int, list[asyncio.Queue]] = {}
        self._max_queue_size = max_queue_size
        self._lock = asyncio.Lock()

    # ── Publish (works from any process / thread / coroutine) ──────────

    async def publish(
        self,
        review_id: int,
        event_type: str,
        message: str = "",
        extra: dict | None = None,
    ) -> int:
        """Broadcast an event to all subscribed clients.

        Args:
            review_id: The review being updated.
            event_type: Event name (e.g. 'review_started', 'finding_added').
            message: Human-readable description.
            extra: Optional extra key-value data to include in the payload.

        Returns:
            Number of clients that received the event (best-effort).
        """
        payload = _make_event(event_type, review_id, message, extra)
        sse_str = format_sse_event(payload, event=event_type)

        # --- Primary path: Redis Pub/Sub ---
        r = _get_redis()
        if r:
            try:
                # Run blocking Redis publish in thread pool so we don't
                # block the asyncio event loop.
                msg = json.dumps({"sse": sse_str, "review_id": review_id, "type": event_type})
                await asyncio.get_event_loop().run_in_executor(
                    None, r.publish, _SSE_CHANNEL, msg
                )
                logger.debug(
                    "SSE Redis publish: review_id=%d type=%s", review_id, event_type
                )
                return 1  # Redis delivers to all subscribers; we don't know exact client count
            except Exception as e:
                logger.warning("SSE Redis publish failed (%s), falling back to in-process queue", e)

        # --- Fallback path: in-process queues (single-process use only) ---
        async with self._lock:
            queues = list(self._queues.get(review_id, []))

        sent = 0
        for q in queues:
            try:
                q.put_nowait(sse_str)
                sent += 1
            except asyncio.QueueFull:
                logger.warning(
                    "SSE fallback queue full for review_id=%d — dropping event %s",
                    review_id, event_type,
                )

        logger.debug(
            "SSE fallback publish: review_id=%d type=%s clients=%d",
            review_id, event_type, sent,
        )
        return sent

    # ── Convenience publish methods ────────────────────────────────────

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

    async def publish_prologue_generated(self, review_id: int) -> None:
        await self.publish(
            review_id, "prologue_generated",
            message="Prologue synthesis completed."
        )

    async def publish_chapter_started(self, review_id: int, chapter_id: int) -> None:
        await self.publish(
            review_id, "chapter_started",
            message=f"Started reviewing chapter {chapter_id}",
            extra={"chapter_id": chapter_id},
        )

    async def publish_chapter_completed(self, review_id: int, chapter_id: int) -> None:
        await self.publish(
            review_id, "chapter_completed",
            message=f"Completed reviewing chapter {chapter_id}",
            extra={"chapter_id": chapter_id},
        )

    # ── Subscribe (called from FastAPI SSE route) ──────────────────────

    async def subscribe(
        self,
        review_id: int,
        timeout_seconds: float = 300.0,
    ) -> AsyncGenerator[str, None]:
        """Async generator that yields SSE-formatted strings for a review.

        Tries Redis Pub/Sub first (works cross-process with Celery).
        Falls back to in-process asyncio.Queue if Redis is unavailable.

        Args:
            review_id: Which review to subscribe to.
            timeout_seconds: Max time to wait for events before auto-closing.

        Yields:
            SSE-formatted strings to stream to the client.
        """
        # Send initial heartbeat so browser doesn't time out immediately
        yield format_sse_event(
            _make_event("connected", review_id, "SSE stream connected"),
            event="connected",
        )

        r = _get_redis()
        if r:
            async for chunk in self._subscribe_redis(review_id, timeout_seconds):
                yield chunk
        else:
            async for chunk in self._subscribe_inprocess(review_id, timeout_seconds):
                yield chunk

    async def _subscribe_redis(
        self,
        review_id: int,
        timeout_seconds: float,
    ) -> AsyncGenerator[str, None]:
        """Subscribe via Redis Pub/Sub (works cross-process)."""
        import redis as _redis

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=self._max_queue_size)

        # Redis subscribe runs in a background thread; it puts events onto
        # the asyncio queue so we can yield them in the async generator.
        stop_event = threading.Event()

        def _redis_listener():
            try:
                r_sync = _get_redis()
                if not r_sync:
                    return
                pubsub = r_sync.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(_SSE_CHANNEL)
                for message in pubsub.listen():
                    if stop_event.is_set():
                        break
                    if message and message.get("type") == "message":
                        try:
                            data = json.loads(message["data"])
                            # Filter to events for this review_id OR broadcast events
                            msg_review_id = data.get("review_id")
                            if msg_review_id is None or msg_review_id == review_id:
                                sse_str = data.get("sse", "")
                                if sse_str:
                                    # Put onto asyncio queue from thread
                                    loop.call_soon_threadsafe(queue.put_nowait, sse_str)
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("SSE Redis listener error: %s", e)
            finally:
                # Signal generator to stop
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, None)
                except Exception:
                    pass

        listener_thread = threading.Thread(target=_redis_listener, daemon=True)
        listener_thread.start()
        logger.info("SSE Redis subscriber started: review_id=%d", review_id)

        try:
            import time
            start = time.monotonic()
            while True:
                elapsed = time.monotonic() - start
                remaining = timeout_seconds - elapsed
                if remaining <= 0:
                    yield ": keepalive\n\n"
                    break

                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=min(30.0, remaining))
                    if chunk is None:
                        break  # Listener signaled stop
                    yield chunk
                    # Terminate after final events
                    if '"review_completed"' in chunk or '"review_failed"' in chunk:
                        break
                except asyncio.TimeoutError:
                    # Send keepalive comment line so connection stays open
                    yield ": keepalive\n\n"
        finally:
            stop_event.set()
            logger.info("SSE Redis subscriber closed: review_id=%d", review_id)

    async def _subscribe_inprocess(
        self,
        review_id: int,
        timeout_seconds: float,
    ) -> AsyncGenerator[str, None]:
        """Fallback: subscribe via in-process asyncio.Queue (single-process only)."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)

        async with self._lock:
            if review_id not in self._queues:
                self._queues[review_id] = []
            self._queues[review_id].append(queue)

        logger.info("SSE in-process subscriber started: review_id=%d", review_id)

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=timeout_seconds)
                    yield chunk
                    if '"review_completed"' in chunk or '"review_failed"' in chunk:
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            async with self._lock:
                queues = self._queues.get(review_id, [])
                if queue in queues:
                    queues.remove(queue)
                if not queues and review_id in self._queues:
                    del self._queues[review_id]
            logger.info("SSE in-process subscriber closed: review_id=%d", review_id)

    # ── Introspection ──────────────────────────────────────────────────

    @property
    def active_subscriptions(self) -> dict[int, int]:
        """Return {review_id: client_count} for in-process fallback queues."""
        return {rid: len(qs) for rid, qs in self._queues.items() if qs}

    @property
    def total_clients(self) -> int:
        """Return total in-process client count."""
        return sum(len(qs) for qs in self._queues.values())


# ── Singleton ──────────────────────────────────────────────────────────

sse_manager: SSEManager = SSEManager()
