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
from api.routes.settings import router as settings_router
from api.routes.integrations import router as integrations_router
from api.routes.chapters import router as chapters_router
from api.routes.comments import router as comments_router
from api.routes.local_review import router as local_review_router
from api.webhook import router as github_webhook_router
from providers.gitlab_webhook import router as gitlab_webhook_router

app.include_router(repositories_router, prefix="/api/v3")
app.include_router(reviews_router, prefix="/api/v3")
app.include_router(events_router, prefix="/api/v3")
app.include_router(analytics_router, prefix="/api/v3")
app.include_router(settings_router, prefix="/api/v3")
app.include_router(integrations_router, prefix="/api/v3")
app.include_router(chapters_router, prefix="/api/v3")
app.include_router(comments_router, prefix="/api/v3")
app.include_router(local_review_router, prefix="/api/v3")
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
    
    # --- Pyngrok Integration ---
    try:
        from pyngrok import ngrok
        if settings.NGROK_AUTH_TOKEN:
            ngrok.set_auth_token(settings.NGROK_AUTH_TOKEN)
        else:
            logger.warning("NGROK_AUTH_TOKEN not set — tunnel may be rate-limited")
        ngrok.kill()  # Kill any stale tunnels from previous runs
        tunnel = ngrok.connect(settings.API_PORT)
        public_url = tunnel.public_url
        webhook_url = f"{public_url}/api/v3/github/webhook"

        logger.info("=" * 60)
        logger.info(f"ngrok tunnel active: {public_url}")
        logger.info(f"GitHub Webhook URL : {webhook_url}")
        logger.info("ACTION REQUIRED: Update your GitHub repo webhook to the URL above")
        logger.info("  Settings → Webhooks → Edit → Payload URL")
        logger.info("=" * 60)

        # Save URL to file so it's easy to find after log scrolls away
        try:
            import pathlib
            url_file = pathlib.Path(".ngrok_url")
            url_file.write_text(
                f"Webhook URL: {webhook_url}\nBase URL: {public_url}\n",
                encoding="utf-8",
            )
            logger.info(f"ngrok URL saved to .ngrok_url")
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"Failed to start ngrok tunnel: {e}")
    # ---------------------------

    # Initialize DB — retry until Postgres is ready (handles "starting up" race condition)
    from models.database import is_using_sqlite
    backend = "SQLite (fallback)" if is_using_sqlite() else "PostgreSQL"
    logger.info(f"Waiting for database ({backend}) to be ready...")
    
    max_retries = 15
    retry_delay = 2  # seconds
    for attempt in range(1, max_retries + 1):
        try:
            db_ok = await check_connection()
            if db_ok:
                await create_all_tables()
                logger.info(f"Database ({backend}) connected and tables created.")
                break
            else:
                raise Exception("check_connection returned False")
        except Exception as exc:
            if attempt < max_retries:
                logger.warning(
                    f"Database not ready (attempt {attempt}/{max_retries}): {exc!r}. "
                    f"Retrying in {retry_delay}s..."
                )
                await asyncio.sleep(retry_delay)
            else:
                logger.error(
                    f"Database failed to become ready after {max_retries} attempts. "
                    "API will start but DB endpoints will return errors."
                )
    # Initialize Persistent RAG Indexes asynchronously
    try:
        from models.database import get_db_session_context
        from models.repositories import RepositoryRepo
        async with get_db_session_context() as session:
            repos = await RepositoryRepo.get_all_active(session)
            if repos:
                logger.info(f"Dispatching RAG index updates for {len(repos)} active repositories...")
                from workers.rag_worker import update_repo_rag_index
                for repo in repos:
                    update_repo_rag_index.delay(repo.id)
    except Exception as e:
        logger.warning(f"Failed to dispatch initial RAG index tasks: {e}")

    # Start SSE Keepalive is handled dynamically in subscribe()

    # Start GitHub/GitLab Poller if enabled
    if settings.POLLING_ENABLED:
        from providers.gitlab_poller import GitLabPoller
        gitlab_poller = GitLabPoller()
        asyncio.create_task(gitlab_poller.start())
        logger.info("GitLab Poller started.")

        if settings.GITHUB_REPO:
            from api.poller import GitHubPoller
            github_poller = GitHubPoller()
            asyncio.get_event_loop().run_in_executor(None, github_poller.start)
            logger.info("GitHub Poller started.")
        else:
            logger.info("GitHub Poller skipped — GITHUB_REPO not configured (using webhooks).")

    else:
        logger.info("Polling disabled — using webhooks.")



# ─── Base Endpoints ───────────────────────────────────────────────────────────

@app.get("/status")
@app.get("/api/v3/status")
@app.get("/health")
async def get_status():
    from models.database import is_using_sqlite
    db_connected = await check_connection()
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "3.0.0",
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "database": db_connected,
        "database_backend": "sqlite" if is_using_sqlite() else "postgresql",
    }


@app.get("/")
async def root():
    return {"message": "DevAssist AI API v3.0", "docs": "/docs"}




if __name__ == "__main__":
    
    uvicorn.run("api.main:app", host=settings.API_HOST, port=settings.API_PORT, reload=True)
