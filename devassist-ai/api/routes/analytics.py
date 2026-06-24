"""
DevAssist AI — Analytics API Route
Aggregates review and finding statistics for the frontend Analytics page.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from models.database import get_db_session

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("")
async def get_analytics(session: AsyncSession = Depends(get_db_session)):
    """Return aggregated analytics: review counts, finding breakdown by severity & category."""
    from models.entities import Review, Finding, Repository

    # ── Review counts ─────────────────────────────────────────────────────────
    review_stats_rows = await session.execute(
        select(Review.status, func.count(Review.id).label("cnt"))
        .group_by(Review.status)
    )
    review_by_status: dict[str, int] = {row.status: row.cnt for row in review_stats_rows}

    total_reviews = sum(review_by_status.values())
    review_stats = {
        "total": total_reviews,
        "completed": review_by_status.get("COMPLETED", 0),
        "failed": review_by_status.get("FAILED", 0),
        "running": review_by_status.get("RUNNING", 0),
    }

    # ── Repository count ──────────────────────────────────────────────────────
    repo_count_result = await session.execute(
        select(func.count(Repository.id)).where(Repository.is_active == True)
    )
    total_repositories: int = repo_count_result.scalar_one_or_none() or 0

    # ── Finding counts by severity ────────────────────────────────────────────
    sev_rows = await session.execute(
        select(Finding.severity, func.count(Finding.id).label("cnt"))
        .where(Finding.is_suppressed == False)
        .group_by(Finding.severity)
    )
    sev_map: dict[str, int] = {row.severity.lower(): row.cnt for row in sev_rows}
    findings_by_severity = {
        "critical": sev_map.get("critical", 0),
        "high": sev_map.get("high", 0),
        "medium": sev_map.get("medium", 0),
        "low": sev_map.get("low", 0),
    }
    total_findings = sum(findings_by_severity.values())

    # ── Finding counts by category ────────────────────────────────────────────
    cat_rows = await session.execute(
        select(Finding.category, func.count(Finding.id).label("cnt"))
        .where(Finding.is_suppressed == False)
        .group_by(Finding.category)
        .order_by(func.count(Finding.id).desc())
        .limit(10)
    )
    findings_by_category = [
        {"name": row.category, "count": row.cnt} for row in cat_rows if row.category
    ]

    # ── Avg findings per review ───────────────────────────────────────────────
    completed = review_stats["completed"]
    avg_findings_per_review = (total_findings / completed) if completed > 0 else 0.0

    return {
        "reviews": review_stats,
        "findings_by_severity": findings_by_severity,
        "findings_by_category": findings_by_category,
        "total_findings": total_findings,
        "total_repositories": total_repositories,
        "avg_findings_per_review": round(avg_findings_per_review, 2),
    }
