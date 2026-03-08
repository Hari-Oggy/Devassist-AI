"""
DevAssist AI — FastAPI Application.

Supports two modes of operation:
  1. Async mode (with Celery + Redis): POST /review and POST /document enqueue tasks
     and return task IDs. Poll GET /task/{task_id} for results.
  2. Sync mode (fallback): If Redis/Celery is unavailable, runs agents inline.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from datetime import datetime
from typing import Optional, List, Dict, Any

from core.config import get_settings
from core.logger import get_logger

logger = get_logger("api")
settings = get_settings()

app = FastAPI(title="DevAssist AI API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount webhook router
from api.webhook import router as webhook_router
app.include_router(webhook_router)


# ─── Models ───────────────────────────────────────────────────────────────────

class ReviewRequest(BaseModel):
    pr_number: int

class DocumentRequest(BaseModel):
    file_path: str
    save_updated: bool = False

class TaskResponse(BaseModel):
    """Returned when a task is enqueued."""
    task_id: str
    status: str = "queued"
    message: str = ""

class ReviewResponse(BaseModel):
    pr_number: int
    comments: List[Dict[str, Any]] = []
    files_reviewed: List[str] = []
    audit_log: List[str] = []
    model_used: str = ""
    provider_used: str = ""
    timestamp: str = ""
    success: bool = True
    error: Optional[str] = None

class DocumentResponse(BaseModel):
    file_path: str
    updated_code: Optional[str] = None
    markdown: Optional[str] = None
    changes_made: int = 0
    items_documented: List[str] = []
    model_used: str = ""
    provider_used: str = ""
    timestamp: str = ""
    success: bool = True
    error: Optional[str] = None


# ─── In-memory history ────────────────────────────────────────────────────────
review_history: list = []
doc_history: list = []


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


# ─── API Key Auth ─────────────────────────────────────────────────────────────

from fastapi import Security, Depends
from fastapi.security import APIKeyHeader

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(_api_key_header)):
    """Verify API key for protected endpoints. Skipped if API_KEY is not set."""
    if settings.API_KEY and api_key != settings.API_KEY:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Invalid or missing X-API-Key")
    return True


# ─── Events ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    logger.info(f"DevAssist AI API v2.0 running on http://{settings.API_HOST}:{settings.API_PORT}")
    logger.info(f"LLM Provider: {settings.LLM_PROVIDER} | Model: {settings.LLM_MODEL}")

    # Start GitHub Poller if enabled
    if settings.POLLING_ENABLED:
        from api.poller import get_poller
        poller = get_poller()
        poller.start()
        logger.info(f"GitHub Poller started (interval: {settings.POLLING_INTERVAL}s)")
    else:
        logger.info("Polling disabled — use webhooks or manual trigger")


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/review", dependencies=[Depends(verify_api_key)])
async def create_review(request: ReviewRequest):
    """
    Start a PR review.
    If Celery/Redis is available → enqueue and return task_id.
    Otherwise → run synchronously and return result.
    """
    timestamp = datetime.now().isoformat()

    if _celery_available():
        from workers.review_worker import run_review
        task = run_review.delay(request.pr_number)
        return TaskResponse(task_id=task.id, status="queued", message=f"Review for PR #{request.pr_number} queued.")

    # Fallback: synchronous execution
    try:
        from agents.review_agent import ReviewAgent
        agent = ReviewAgent()
        result = agent.review_pr(request.pr_number)
        response = ReviewResponse(
            pr_number=request.pr_number,
            comments=result.get("comments", []),
            files_reviewed=result.get("files_reviewed", []),
            audit_log=result.get("audit_log", []),
            model_used=result.get("model_used", ""),
            provider_used=result.get("provider_used", ""),
            timestamp=timestamp,
            success=result.get("success", True),
            error=result.get("error"),
        )
        review_history.append(response.dict())
        return response
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg:
            error_msg = f"Rate limited by LLM provider. Please try again later. ({error_msg})"
        return ReviewResponse(pr_number=request.pr_number, timestamp=timestamp, success=False, error=error_msg)


@app.post("/document", dependencies=[Depends(verify_api_key)])
async def create_document(request: DocumentRequest):
    """
    Start documentation generation.
    If Celery/Redis is available → enqueue and return task_id.
    Otherwise → run synchronously and return result.
    """
    timestamp = datetime.now().isoformat()

    if _celery_available():
        from workers.doc_worker import run_documentation
        task = run_documentation.delay(request.file_path, request.save_updated)
        return TaskResponse(task_id=task.id, status="queued", message=f"Documentation for {request.file_path} queued.")

    # Fallback: synchronous execution
    try:
        from agents.doc_agent import DocumentationAgent
        agent = DocumentationAgent()
        result = agent.process_file(request.file_path, request.save_updated)
        response = DocumentResponse(
            file_path=request.file_path,
            updated_code=result.get("updated_code"),
            markdown=result.get("markdown"),
            changes_made=result.get("changes_made", 0),
            items_documented=result.get("items_documented", []),
            model_used=result.get("model_used", ""),
            provider_used=result.get("provider_used", ""),
            timestamp=timestamp,
            success=result.get("success", True),
            error=result.get("error"),
        )
        doc_history.append(response.dict())
        return response
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg:
            error_msg = f"Rate limited by LLM provider. Please try again later. ({error_msg})"
        return DocumentResponse(file_path=request.file_path, timestamp=timestamp, success=False, error=error_msg)


@app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """Poll for the result of an async task."""
    try:
        from taskqueue.celery_app import celery_app
        result = celery_app.AsyncResult(task_id)
        response = {
            "task_id": task_id,
            "status": result.status,
        }
        if result.ready():
            if result.successful():
                try:
                    response["result"] = result.get(timeout=5)
                except Exception as e:
                    response["result"] = {"success": False, "error": f"Failed to retrieve result: {e}"}
            else:
                # Task raised an exception
                response["error"] = str(result.result) if result.result else "Task failed with unknown error"
        return response
    except Exception as e:
        return {"task_id": task_id, "status": "error", "error": str(e)}


@app.get("/history/reviews")
async def get_review_history():
    return review_history[-20:]


@app.get("/history/docs")
async def get_doc_history():
    return doc_history[-20:]


@app.get("/status")
async def get_status():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
    }


@app.get("/health")
async def health_check():
    """Detailed health check: LLM Router, Redis, RAG index."""
    status = {"status": "ok", "components": {}}

    # LLM Router — test the configured provider with a minimal call
    try:
        from llm.router import LLMRouter, _get_provider
        from llm.registry import get_model_info
        model_info = get_model_info(settings.LLM_MODEL)
        if model_info:
            provider = _get_provider(model_info["provider"])
            status["components"]["llm_router"] = f"ok ({settings.LLM_PROVIDER}/{settings.LLM_MODEL})"
        else:
            status["components"]["llm_router"] = f"unknown model: {settings.LLM_MODEL}"
            status["status"] = "degraded"
    except Exception as e:
        status["components"]["llm_router"] = f"error: {str(e)}"
        status["status"] = "degraded"

    # Redis / Celery
    if _celery_available():
        status["components"]["redis_queue"] = "ok"
    else:
        status["components"]["redis_queue"] = "unavailable (sync fallback active)"

    # FAISS Index
    index_path = settings.FAISS_INDEX_PATH
    if os.path.exists(index_path):
        status["components"]["rag_index"] = "ok"
    else:
        status["components"]["rag_index"] = "missing — run scripts/setup_index.py"
        status["status"] = "degraded"

    return status


@app.get("/")
async def root():
    return {"message": "DevAssist AI API v2.0", "docs": "/docs"}


if __name__ == "__main__":
    uvicorn.run("api.main:app", host=settings.API_HOST, port=settings.API_PORT, reload=True)
