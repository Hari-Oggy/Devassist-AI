import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api.sse import sse_manager

router = APIRouter(prefix="/events", tags=["SSE Events"])

@router.get("/{review_id}")
async def sse_endpoint(review_id: int, request: Request):
    """
    Subscribe to live updates for a specific review.
    Clients connect using EventSource to receive server-sent events.
    """
    async def event_generator():
        try:
            async for event in sse_manager.subscribe(review_id):
                if await request.is_disconnected():
                    break
                yield event
        except asyncio.CancelledError:
            pass
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
