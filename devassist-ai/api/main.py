"""
DevAssist AI — FastAPI Application V3.0

Supports:
  1. Webhooks (GitHub / GitLab)
  2. SSE for live review updates
  3. PostgreSQL for persistence
"""

import sys
import os
import asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_settings
from core.logger import get_logger
from models.database import create_all_tables, check_connection
from api.sse import sse_manager

logger = get_logger("api")
settings = get_settings()

app = FastAPI(title="DevAssist AI API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────

from api.routes.repositories import router as repositories_router
from api.routes.reviews import router as reviews_router
from api.routes.events import router as events_router
from api.routes.analytics import router as analytics_router
from api.webhook import router as github_webhook_router
from providers.gitlab_webhook import router as gitlab_webhook_router

app.include_router(repositories_router, prefix="/api/v3")
app.include_router(reviews_router, prefix="/api/v3")
app.include_router(events_router, prefix="/api/v3")
app.include_router(analytics_router, prefix="/api/v3")
app.include_router(github_webhook_router, prefix="/api/v3/github")
app.include_router(gitlab_webhook_router, prefix="/api/v3/gitlab")


# ─── Helpers ──────────────────────────────────────────────────────────────────

_celery_ok = None
_celery_check_time = 0.0

def _celery_available() -> bool:
    """Check if Celery/Redis is reachable. Re-checks every 30 seconds."""
    import time as _time
    global _celery_ok, _celery_check_time
    now = _time.time()
    if _celery_ok is not None and (now - _celery_check_time) < 30:
        return _celery_ok
    _celery_check_time = now
    try:
        from taskqueue.celery_app import celery_app
        celery_app.connection().ensure_connection(max_retries=1, timeout=1)
        _celery_ok = True
    except Exception:
        _celery_ok = False
    return _celery_ok


# ─── Events ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    logger.info(f"DevAssist AI API v3.0 running on http://{settings.API_HOST}:{settings.API_PORT}")
    
    # Initialize DB
    logger.info("Initializing database...")
    db_ok = await check_connection()
    if db_ok:
        await create_all_tables()
    else:
        logger.warning("Database connection failed on startup. Is PostgreSQL running?")
    
    # Start SSE Keepalive is handled dynamically in subscribe()

    # Start GitHub/GitLab Poller if enabled
    if settings.POLLING_ENABLED:
        from providers.gitlab_poller import GitLabPoller
        poller = GitLabPoller()
        asyncio.create_task(poller.start())
        logger.info("GitLab Poller started.")
    else:
        logger.info("Polling disabled — using webhooks.")


# ─── Base Endpoints ───────────────────────────────────────────────────────────

@app.get("/status")
@app.get("/api/v3/status")
async def get_status():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "3.0.0",
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "database": await check_connection()
    }


@app.get("/")
async def root():
    return {"message": "DevAssist AI API v3.0", "docs": "/docs"}


if __name__ == "__main__":
    uvicorn.run("api.main:app", host=settings.API_HOST, port=settings.API_PORT, reload=True)
