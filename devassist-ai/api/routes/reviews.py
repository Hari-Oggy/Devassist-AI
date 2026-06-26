from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any

from models.database import get_db_session
from models.repositories import PullRequestRepo, ReviewRepo, FindingRepo, ReviewEventRepo
from pydantic import BaseModel

router = APIRouter(prefix="/reviews", tags=["Reviews"])

# ── Schemas ─────────────────────────────────────────────────────────────

class ReviewTriggerRequest(BaseModel):
    provider: str
    repo_full_name: str
    pr_number: int

class FindingResponse(BaseModel):
    id: int
    file_path: str
    line_start: int
    severity: str
    category: str
    message: str
    code_fix: str | None = None
    tool_source: str
    is_suppressed: bool

# ── Endpoints ───────────────────────────────────────────────────────────

@router.get("")
async def get_all_reviews(
    session: AsyncSession = Depends(get_db_session)
):
    """List all reviews."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from models.entities import Review, PullRequest, Repository
    
    # Fetch reviews with their associated PRs and Repos
    stmt = select(Review).options(
        selectinload(Review.pull_request).selectinload(PullRequest.repository)
    ).order_by(Review.created_at.desc()).limit(50)
    
    result = await session.execute(stmt)
    reviews = result.scalars().all()
    
    return [
        {
            "id": r.id,
            "status": r.status,
            "summary": r.raw_summary,
            "commit_sha": r.commit_sha,
            "created_at": r.created_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "pr_title": r.pull_request.title if r.pull_request else None,
            "pr_number": r.pull_request.provider_pr_id if r.pull_request else None,
            "repo_name": r.pull_request.repository.full_name if r.pull_request and r.pull_request.repository else None,
            "provider": r.pull_request.repository.provider if r.pull_request and r.pull_request.repository else None,
            "total_findings": r.total_findings,
        } for r in reviews
    ]


@router.get("/{review_id}")
async def get_review_by_id(
    review_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from models.entities import Review, PullRequest, Repository
    
    stmt = select(Review).where(Review.id == review_id).options(
        selectinload(Review.pull_request).selectinload(PullRequest.repository)
    )
    result = await session.execute(stmt)
    r = result.scalar_one_or_none()
    
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")
        
    return {
        "id": r.id,
        "status": r.status,
        "summary": r.raw_summary,
        "commit_sha": r.commit_sha,
        "created_at": r.created_at.isoformat(),
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "pr_title": r.pull_request.title if r.pull_request else None,
        "pr_number": r.pull_request.provider_pr_id if r.pull_request else None,
        "repo_name": r.pull_request.repository.full_name if r.pull_request and r.pull_request.repository else None,
        "provider": r.pull_request.repository.provider if r.pull_request and r.pull_request.repository else None,
        "total_findings": r.total_findings,
    }

@router.get("/{review_id}/findings", response_model=List[FindingResponse])
async def get_review_findings(
    review_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    findings = await FindingRepo.list_for_review(session, review_id)
    return [
        {
            "id": f.id,
            "file_path": f.file_path,
            "line_start": f.line_start,
            "severity": f.severity,
            "category": f.category,
            "message": f.message,
            "code_fix": f.code_fix,
            "tool_source": f.tool_source,
            "is_suppressed": f.is_suppressed
        } for f in findings
    ]

@router.get("/{review_id}/events")
async def get_review_audit_log(
    review_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    events = await ReviewEventRepo.list_for_review(session, review_id)
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "message": e.message,
            "created_at": e.created_at.isoformat()
        } for e in events
    ]

@router.post("/trigger")
async def trigger_review_manually(
    request: ReviewTriggerRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session)
):
    """Manually trigger a review via API."""
    # Find PR first
    # pr_repo = PullRequestRepo(session)
    # This assumes PR is already in our DB (upserted by a webhook previously or poller)
    # If not, we'd need to fetch from provider. For manual trigger we just enqueue it
    
    # We use Celery if available, otherwise synchronous
    from api.main import _celery_available
    if _celery_available():
        from workers.review_worker import run_review
        # We need PR ID from DB for run_review. Let's just pass the data we have.
        # But wait, run_review takes pr_id (internal integer).
        # We'll just return a message to use webhooks for now, or we can look it up.
        # For simplicity, returning NotImplemented for manual trigger.
        raise HTTPException(status_code=501, detail="Manual trigger requires passing internal PR ID. Use provider webhooks.")
    
    raise HTTPException(status_code=501, detail="Synchronous fallback not implemented in V3.")
