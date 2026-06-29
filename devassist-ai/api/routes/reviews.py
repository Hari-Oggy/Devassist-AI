from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from models.database import get_db_session
from models.repositories import PullRequestRepo, ReviewRepo, FindingRepo, ReviewEventRepo, RepositoryRepo
from pydantic import BaseModel

router = APIRouter(prefix="/reviews", tags=["Reviews"])

# ── Schemas ─────────────────────────────────────────────────────────────

class ReviewTriggerRequest(BaseModel):
    provider: str
    repo_full_name: str
    pr_number: int

class SuppressionRequest(BaseModel):
    reason: str = "False positive"

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

@router.get("/{review_id}/impact")
async def get_review_impact(
    review_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """Return the blast-radius / impact analysis for a completed review.

    The impact data is computed by CodeGraphBuilder + ImpactAnalyzer during
    the review pipeline and persisted into the ``pipeline_meta`` JSON column.
    Returns an empty impact object if the review is not yet complete or the
    impact data was not captured.
    """
    from sqlalchemy import select
    from models.entities import Review

    stmt = select(Review.pipeline_meta, Review.status).where(Review.id == review_id)
    result = await session.execute(stmt)
    row = result.one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Review not found")

    pipeline_meta, status = row
    impact_report = (pipeline_meta or {}).get("impact_report", {})

    return {
        "review_id": review_id,
        "status": status,
        "impact_report": impact_report,
        # Convenience top-level fields for frontend rendering
        "affected_files": impact_report.get("affected_files", []),
        "blast_radius": impact_report.get("blast_radius", 0),
        "changed_files": impact_report.get("changed_files", []),
        "callers": impact_report.get("callers", {}),
    }


@router.post("/trigger")
async def trigger_review_manually(
    request: ReviewTriggerRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """Manually trigger a review via API by repo + PR number.
    
    Looks up the repository from the DB (or creates a placeholder entry),
    then dispatches a Celery review task. Does NOT require the PR to have
    been seen by a webhook first — the worker will fetch the diff from GitHub.
    """
    from workers.review_worker import run_review

    # Resolve or create the repository entry
    repo = await RepositoryRepo.get_by_full_name(
        session, request.provider, request.repo_full_name
    )
    if repo is None:
        # Auto-register the repo so we have a DB record
        repo = await RepositoryRepo.upsert(
            session=session,
            provider=request.provider,
            full_name=request.repo_full_name,
        )
        await session.commit()

    # Build the same context dict the webhook handler produces
    context = {
        "provider": request.provider,
        "project_path": request.repo_full_name,
        "pr_number": request.pr_number,
        "mr_iid": request.pr_number,
        "mr_title": f"PR #{request.pr_number} (manual trigger)",
        "mr_author": "manual",
        "source_branch": "",
        "target_branch": "main",
        "is_draft": False,
        "mr_url": "",
        "last_commit_sha": "",
    }

    # Dispatch via Celery if available; otherwise run synchronously in bg
    from api.main import _celery_available
    if _celery_available():
        task = run_review.delay(context)
        return {
            "status": "queued",
            "task_id": task.id,
            "provider": request.provider,
            "repo": request.repo_full_name,
            "pr_number": request.pr_number,
            "message": "Review task queued. Connect to the SSE stream to follow progress.",
        }

    # Fallback: run in FastAPI background tasks (no Celery)
    import asyncio
    from workers.review_worker import _run_review_async
    asyncio.get_event_loop().create_task(_run_review_async(context))
    return {
        "status": "started",
        "provider": request.provider,
        "repo": request.repo_full_name,
        "pr_number": request.pr_number,
        "message": "Review started (no Celery — running in-process).",
    }


@router.patch("/{review_id}/findings/{finding_id}/suppress", tags=["Findings"])
async def suppress_finding(
    review_id: int,
    finding_id: int,
    body: SuppressionRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """Suppress (dismiss) a finding — marks it as a false positive.
    
    Suppressed findings are retained in the DB but excluded from the
    active findings count. This lets developers dismiss noise without
    losing the audit trail.
    """
    from sqlalchemy import select
    from models.entities import Finding

    # Verify the finding belongs to this review
    stmt = select(Finding).where(
        Finding.id == finding_id,
        Finding.review_id == review_id,
    )
    result = await session.execute(stmt)
    finding = result.scalar_one_or_none()

    if finding is None:
        raise HTTPException(
            status_code=404,
            detail=f"Finding {finding_id} not found on review {review_id}"
        )

    suppressed = await FindingRepo.suppress(session, finding_id, body.reason)
    await session.commit()

    if not suppressed:
        raise HTTPException(status_code=500, detail="Failed to suppress finding")

    return {
        "id": finding_id,
        "review_id": review_id,
        "is_suppressed": True,
        "suppression_reason": body.reason,
        "message": "Finding suppressed successfully.",
    }


@router.delete("/{review_id}/findings/{finding_id}/suppress", tags=["Findings"])
async def unsuppress_finding(
    review_id: int,
    finding_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """Un-suppress a previously suppressed finding."""
    from sqlalchemy import update as sa_update
    from models.entities import Finding

    stmt = (
        sa_update(Finding)
        .where(Finding.id == finding_id, Finding.review_id == review_id)
        .values(is_suppressed=False, suppression_reason=None)
    )
    result = await session.execute(stmt)
    await session.commit()

    if result.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Finding {finding_id} not found on review {review_id}"
        )

    return {
        "id": finding_id,
        "review_id": review_id,
        "is_suppressed": False,
        "message": "Finding un-suppressed successfully.",
    }


@router.delete("/{review_id}")
async def delete_review(
    review_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """Delete a review from the database."""
    from models.entities import Review
    from sqlalchemy import select
    
    stmt = select(Review).where(Review.id == review_id)
    result = await session.execute(stmt)
    review = result.scalar_one_or_none()
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
        
    await session.delete(review)
    await session.commit()
    return {"message": f"Review {review_id} successfully deleted"}

