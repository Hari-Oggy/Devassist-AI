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
    review_by_status: dict[str, int] = {}
    for row in review_stats_rows:
        status_str = row.status.value if hasattr(row.status, "value") else str(row.status)
        review_by_status[status_str.lower()] = row.cnt

    total_reviews = sum(review_by_status.values())
    review_stats = {
        "total": total_reviews,
        "completed": review_by_status.get("completed", 0),
        "failed": review_by_status.get("failed", 0),
        "running": review_by_status.get("running", 0),
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
    sev_map: dict[str, int] = {}
    for row in sev_rows:
        sev_str = row.severity.value if hasattr(row.severity, "value") else str(row.severity)
        sev_map[sev_str.lower()] = row.cnt

    findings_by_severity = {
        "critical": sev_map.get("error", 0),
        "high": sev_map.get("warning", 0),
        "medium": sev_map.get("note", 0),
        "low": 0,
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
        {
            "name": (row.category.value if hasattr(row.category, "value") else str(row.category)),
            "count": row.cnt
        } for row in cat_rows if row.category
    ]

    # ── Avg findings per review ───────────────────────────────────────────────
    completed = review_stats["completed"]
    avg_findings_per_review = (total_findings / completed) if completed > 0 else 0.0

    avg_duration_result = await session.execute(
        select(func.avg(Review.duration_seconds)).where(Review.status == "completed")
    )
    avg_duration_seconds = avg_duration_result.scalar_one_or_none() or 0.0

    return {
        "reviews": review_stats,
        "findings_by_severity": findings_by_severity,
        "findings_by_category": findings_by_category,
        "total_findings": total_findings,
        "total_repositories": total_repositories,
        "avg_findings_per_review": round(avg_findings_per_review, 2),
        "avg_resolution_time": round(avg_duration_seconds, 1),
    }


@router.get("/trends")
async def get_trends(session: AsyncSession = Depends(get_db_session)):
    """Return daily count of findings by severity (critical, high, other) for the last 30 days."""
    from datetime import datetime, timedelta, timezone
    from models.entities import Review, Finding

    # Calculate date range
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=29)
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)

    # Group findings by func.date(Review.created_at) and Finding.severity
    stmt = (
        select(
            func.date(Review.created_at).label("day"),
            Finding.severity.label("severity"),
            func.count(Finding.id).label("cnt")
        )
        .join(Finding, Finding.review_id == Review.id)
        .where(Review.created_at >= start_dt, Finding.is_suppressed == False)
        .group_by(func.date(Review.created_at), Finding.severity)
    )

    result = await session.execute(stmt)
    rows = result.all()

    data_by_day = {}
    for row in rows:
        day_val = row.day
        if not day_val:
            continue
        if isinstance(day_val, str):
            day_str = day_val
        else:
            day_str = day_val.strftime("%Y-%m-%d")
        
        sev_val = row.severity
        sev_str = sev_val.value if hasattr(sev_val, "value") else str(sev_val)
        sev = sev_str.lower()
        
        if "error" in sev:
            sev_key = "critical"
        elif "warning" in sev:
            sev_key = "high"
        else:
            sev_key = "other"

        if day_str not in data_by_day:
            data_by_day[day_str] = {"critical": 0, "high": 0, "other": 0}
        
        data_by_day[day_str][sev_key] += row.cnt

    trends = []
    for i in range(30):
        current_day = start_date + timedelta(days=i)
        day_str = current_day.strftime("%Y-%m-%d")
        day_data = data_by_day.get(day_str, {"critical": 0, "high": 0, "other": 0})
        trends.append({
            "date": day_str,
            "critical": day_data["critical"],
            "high": day_data["high"],
            "other": day_data["other"]
        })
    
    return trends
