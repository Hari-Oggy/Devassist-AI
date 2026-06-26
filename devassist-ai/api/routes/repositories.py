import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from models.database import get_db_session
from models.repositories import RepositoryRepo
from models.entities import ProviderType
from pydantic import BaseModel, Field

router = APIRouter(prefix="/repositories", tags=["Repositories"])

# ── Schemas ─────────────────────────────────────────────────────────────

class RepositoryCreate(BaseModel):
    provider: ProviderType
    full_name: str
    provider_id: int | None = None
    default_branch: str = "main"
    webhook_secret: str | None = None

class RepositoryUpdate(BaseModel):
    is_active: bool | None = None
    default_branch: str | None = None
    webhook_secret: str | None = None

class RepositoryResponse(BaseModel):
    id: int
    provider: ProviderType
    full_name: str
    is_active: bool
    created_at: str
    reviews_count: int = 0
    open_issues: int = 0
    success_rate: int = 100

    class Config:
        from_attributes = True

# ── Endpoints ───────────────────────────────────────────────────────────

@router.get("", response_model=List[RepositoryResponse])
async def list_repositories(
    active_only: bool = Query(True, description="Only return active repos"),
    session: AsyncSession = Depends(get_db_session)
):
    from sqlalchemy import select, func
    from models.entities import Review, PullRequest, Finding, ReviewStatus

    if active_only:
        repos = await RepositoryRepo.get_all_active(session)
    else:
        # TODO: Implement get_all() if needed, for now just returning active
        repos = await RepositoryRepo.get_all_active(session)
    
    results = []
    for r in repos:
        # Count total reviews
        total_stmt = (
            select(func.count(Review.id))
            .join(PullRequest, Review.pull_request_id == PullRequest.id)
            .where(PullRequest.repository_id == r.id)
        )
        total_res = await session.execute(total_stmt)
        reviews_count = total_res.scalar_one_or_none() or 0

        # Count completed reviews
        completed_stmt = (
            select(func.count(Review.id))
            .join(PullRequest, Review.pull_request_id == PullRequest.id)
            .where(PullRequest.repository_id == r.id, Review.status == ReviewStatus.COMPLETED)
        )
        completed_res = await session.execute(completed_stmt)
        completed_reviews = completed_res.scalar_one_or_none() or 0

        # Success rate
        success_rate = 100
        if reviews_count > 0:
            success_rate = int(round((completed_reviews / reviews_count) * 100))

        # Count open issues (open/unsuppressed findings on completed reviews)
        open_issues_stmt = (
            select(func.count(Finding.id))
            .join(Review, Finding.review_id == Review.id)
            .join(PullRequest, Review.pull_request_id == PullRequest.id)
            .where(
                PullRequest.repository_id == r.id,
                Review.status == ReviewStatus.COMPLETED,
                Finding.is_suppressed == False
            )
        )
        open_issues_res = await session.execute(open_issues_stmt)
        open_issues = open_issues_res.scalar_one_or_none() or 0

        results.append({
            "id": r.id,
            "provider": r.provider,
            "full_name": r.full_name,
            "is_active": r.is_active,
            "created_at": r.created_at.isoformat(),
            "reviews_count": reviews_count,
            "open_issues": open_issues,
            "success_rate": success_rate
        })
    return results

@router.post("", response_model=RepositoryResponse)
async def create_repository(
    repo_in: RepositoryCreate,
    session: AsyncSession = Depends(get_db_session)
):
    # Construct Git clone URL
    from core.config import get_settings
    import os
    settings = get_settings()
    if repo_in.provider == ProviderType.GITLAB:
        gitlab_token = getattr(settings, "GITLAB_TOKEN", None) or ""
        gitlab_api_url = getattr(settings, "GITLAB_API_URL", None) or "https://gitlab.com"
        from urllib.parse import urlparse
        parsed = urlparse(gitlab_api_url)
        host = parsed.netloc or "gitlab.com"
        scheme = parsed.scheme or "https"
        if gitlab_token:
            repo_url = f"{scheme}://oauth2:{gitlab_token}@{host}/{repo_in.full_name}.git"
        else:
            repo_url = f"{scheme}://{host}/{repo_in.full_name}.git"
    else:
        github_token = settings.GITHUB_TOKEN or os.getenv("GITHUB_TOKEN")
        if github_token and github_token != "your_github_personal_access_token_here":
            repo_url = f"https://x-access-token:{github_token}@github.com/{repo_in.full_name}.git"
        else:
            repo_url = f"https://github.com/{repo_in.full_name}.git"

    # Validate reachable via RepoCloner
    from codegraph.repo_cloner import RepoCloner
    try:
        with RepoCloner(repo_url=repo_url) as cloner:
            await asyncio.to_thread(cloner.get_repo_path)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to clone repository. Make sure it is reachable and token is valid: {str(e)}"
        )

    db_repo = await RepositoryRepo.upsert(
        session=session,
        provider=repo_in.provider,
        full_name=repo_in.full_name,
        provider_id=repo_in.provider_id,
        default_branch=repo_in.default_branch,
        webhook_secret=repo_in.webhook_secret
    )
    return {
        "id": db_repo.id,
        "provider": db_repo.provider,
        "full_name": db_repo.full_name,
        "is_active": db_repo.is_active,
        "created_at": db_repo.created_at.isoformat(),
        "reviews_count": 0,
        "open_issues": 0,
        "success_rate": 100
    }

@router.delete("/{repo_id}")
async def deactivate_repository(
    repo_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    await RepositoryRepo.deactivate(session, repo_id)
    return {"message": f"Repository {repo_id} deactivated."}
