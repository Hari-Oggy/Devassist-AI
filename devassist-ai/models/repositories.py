"""
Repository Pattern — Data Access Layer for DevAssist-AI Phase 5.

Provides async repository classes that encapsulate all database queries.
Never exposes SQLAlchemy internals to the API layer — the API only calls
these repository methods.

Design:
    - All methods are async and accept an AsyncSession
    - Repositories are stateless — no session stored on the object
    - Consistent return types: entity or None, list of entities
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.logger import get_logger
from models.entities import (
    EventType,
    Finding,
    FindingSeverity,
    PullRequest,
    Repository,
    Review,
    ReviewEvent,
    ReviewStatus,
)

logger = get_logger("models.repositories")


# ── Repository Repository ──────────────────────────────────────────────

class RepositoryRepo:
    """Data access methods for the Repository entity."""

    @staticmethod
    async def get_by_id(session: AsyncSession, repo_id: int) -> Optional[Repository]:
        result = await session.get(Repository, repo_id)
        return result

    @staticmethod
    async def get_by_full_name(
        session: AsyncSession, provider: str, full_name: str
    ) -> Optional[Repository]:
        stmt = select(Repository).where(
            Repository.provider == provider,
            Repository.full_name == full_name,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_active(session: AsyncSession) -> list[Repository]:
        stmt = select(Repository).where(Repository.is_active.is_(True))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def upsert(
        session: AsyncSession,
        provider: str,
        full_name: str,
        provider_id: Optional[int] = None,
        default_branch: str = "main",
        webhook_secret: Optional[str] = None,
    ) -> Repository:
        """Insert or return an existing Repository."""
        repo = await RepositoryRepo.get_by_full_name(session, provider, full_name)
        if repo is None:
            repo = Repository(
                provider=provider,
                full_name=full_name,
                provider_id=provider_id,
                default_branch=default_branch,
                webhook_secret=webhook_secret,
            )
            session.add(repo)
            await session.flush()
            logger.info("Created repository: %s/%s", provider, full_name)
        return repo

    @staticmethod
    async def deactivate(session: AsyncSession, repo_id: int) -> bool:
        stmt = (
            update(Repository)
            .where(Repository.id == repo_id)
            .values(is_active=False)
        )
        result = await session.execute(stmt)
        return result.rowcount > 0


# ── PullRequest Repository ─────────────────────────────────────────────

class PullRequestRepo:
    """Data access methods for the PullRequest entity."""

    @staticmethod
    async def get_by_provider_id(
        session: AsyncSession, repository_id: int, provider_pr_id: int
    ) -> Optional[PullRequest]:
        stmt = select(PullRequest).where(
            PullRequest.repository_id == repository_id,
            PullRequest.provider_pr_id == provider_pr_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert(
        session: AsyncSession,
        repository_id: int,
        provider_pr_id: int,
        title: str = "",
        author: Optional[str] = None,
        source_branch: Optional[str] = None,
        target_branch: Optional[str] = None,
        is_draft: bool = False,
        state: str = "open",
        provider_url: Optional[str] = None,
        diff_size: int = 0,
    ) -> PullRequest:
        pr = await PullRequestRepo.get_by_provider_id(
            session, repository_id, provider_pr_id
        )
        if pr is None:
            pr = PullRequest(
                repository_id=repository_id,
                provider_pr_id=provider_pr_id,
                title=title,
                author=author,
                source_branch=source_branch,
                target_branch=target_branch,
                is_draft=is_draft,
                state=state,
                provider_url=provider_url,
                diff_size=diff_size,
            )
            session.add(pr)
            await session.flush()
        else:
            pr.title = title
            pr.state = state
            pr.is_draft = is_draft
            pr.diff_size = diff_size
        return pr

    @staticmethod
    async def list_open(
        session: AsyncSession, repository_id: int, limit: int = 50
    ) -> list[PullRequest]:
        stmt = (
            select(PullRequest)
            .where(
                PullRequest.repository_id == repository_id,
                PullRequest.state == "open",
            )
            .order_by(desc(PullRequest.updated_at))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ── Review Repository ──────────────────────────────────────────────────

class ReviewRepo:
    """Data access methods for the Review entity."""

    @staticmethod
    async def create(
        session: AsyncSession,
        pull_request_id: int,
        mode: str = "fast",
        commit_sha: Optional[str] = None,
    ) -> Review:
        review = Review(
            pull_request_id=pull_request_id,
            status=ReviewStatus.PENDING,
            mode=mode,
            commit_sha=commit_sha,
        )
        session.add(review)
        await session.flush()
        logger.info("Created review #%d for PR %d", review.id, pull_request_id)
        return review

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        review_id: int,
        with_findings: bool = False,
    ) -> Optional[Review]:
        stmt = select(Review).where(Review.id == review_id)
        if with_findings:
            stmt = stmt.options(selectinload(Review.findings))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_running(session: AsyncSession, review_id: int) -> None:
        stmt = (
            update(Review)
            .where(Review.id == review_id)
            .values(status=ReviewStatus.RUNNING)
        )
        await session.execute(stmt)

    @staticmethod
    async def mark_completed(
        session: AsyncSession,
        review_id: int,
        total_findings: int = 0,
        error_count: int = 0,
        warning_count: int = 0,
        duration_seconds: float = 0.0,
        total_tokens_input: int = 0,
        total_tokens_output: int = 0,
        cost_estimate: float = 0.0,
        model_used: str = "",
        provider_used: str = "",
        raw_summary: Optional[str] = None,
        pipeline_meta: Optional[dict] = None,
    ) -> None:
        stmt = (
            update(Review)
            .where(Review.id == review_id)
            .values(
                status=ReviewStatus.COMPLETED,
                completed_at=datetime.now(timezone.utc),
                total_findings=total_findings,
                error_count=error_count,
                warning_count=warning_count,
                duration_seconds=duration_seconds,
                total_tokens_input=total_tokens_input,
                total_tokens_output=total_tokens_output,
                cost_estimate=cost_estimate,
                model_used=model_used,
                provider_used=provider_used,
                raw_summary=raw_summary,
                pipeline_meta=pipeline_meta,
            )
        )
        await session.execute(stmt)

    @staticmethod
    async def mark_failed(
        session: AsyncSession, review_id: int, error_message: str
    ) -> None:
        stmt = (
            update(Review)
            .where(Review.id == review_id)
            .values(
                status=ReviewStatus.FAILED,
                completed_at=datetime.now(timezone.utc),
                error_message=error_message,
            )
        )
        await session.execute(stmt)

    @staticmethod
    async def list_for_pr(
        session: AsyncSession, pull_request_id: int, limit: int = 10
    ) -> list[Review]:
        stmt = (
            select(Review)
            .where(Review.pull_request_id == pull_request_id)
            .order_by(desc(Review.created_at))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_stats(session: AsyncSession, repository_id: int) -> dict:
        """Return aggregate review stats for a repository."""
        stmt = (
            select(
                func.count(Review.id).label("total_reviews"),
                func.avg(Review.total_findings).label("avg_findings"),
                func.avg(Review.duration_seconds).label("avg_duration"),
                func.sum(Review.cost_estimate).label("total_cost"),
            )
            .join(PullRequest, Review.pull_request_id == PullRequest.id)
            .where(PullRequest.repository_id == repository_id)
        )
        result = await session.execute(stmt)
        row = result.one()
        return {
            "total_reviews": row.total_reviews or 0,
            "avg_findings": float(row.avg_findings or 0),
            "avg_duration_seconds": float(row.avg_duration or 0),
            "total_cost_usd": float(row.total_cost or 0),
        }


# ── Finding Repository ─────────────────────────────────────────────────

class FindingRepo:
    """Data access methods for the Finding entity."""

    @staticmethod
    async def bulk_create(
        session: AsyncSession, review_id: int, findings: list[dict]
    ) -> list[Finding]:
        """Insert multiple findings from a list of dicts.

        Each dict should have keys: file_path, line_start, line_end,
        severity, category, rule_id, tool_source, message, code_fix,
        confidence.
        """
        entities: list[Finding] = []
        for f in findings:
            entity = Finding(
                review_id=review_id,
                file_path=f.get("file_path", f.get("file", "")),
                line_start=f.get("line_start", f.get("line", 0)),
                line_end=f.get("line_end", f.get("line", 0)),
                severity=f.get("severity", FindingSeverity.WARNING),
                category=f.get("category", "maintainability"),
                rule_id=f.get("rule_id", ""),
                tool_source=f.get("tool_source", f.get("tool", "llm")),
                message=f.get("message", f.get("comment", "")),
                code_fix=f.get("code_fix"),
                confidence=f.get("confidence", 1.0),
            )
            entities.append(entity)
        session.add_all(entities)
        await session.flush()
        return entities

    @staticmethod
    async def list_for_review(
        session: AsyncSession, review_id: int
    ) -> list[Finding]:
        stmt = (
            select(Finding)
            .where(Finding.review_id == review_id)
            .order_by(Finding.severity, Finding.file_path, Finding.line_start)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def suppress(
        session: AsyncSession, finding_id: int, reason: str
    ) -> bool:
        stmt = (
            update(Finding)
            .where(Finding.id == finding_id)
            .values(is_suppressed=True, suppression_reason=reason)
        )
        result = await session.execute(stmt)
        return result.rowcount > 0


# ── ReviewEvent Repository ─────────────────────────────────────────────

class ReviewEventRepo:
    """Data access methods for the ReviewEvent entity."""

    @staticmethod
    async def create(
        session: AsyncSession,
        review_id: int,
        event_type: str,
        message: str = "",
        data: Optional[dict] = None,
    ) -> ReviewEvent:
        event = ReviewEvent(
            review_id=review_id,
            event_type=event_type,
            message=message,
            data=data,
        )
        session.add(event)
        await session.flush()
        return event

    @staticmethod
    async def list_for_review(
        session: AsyncSession, review_id: int, limit: int = 50
    ) -> list[ReviewEvent]:
        stmt = (
            select(ReviewEvent)
            .where(ReviewEvent.review_id == review_id)
            .order_by(ReviewEvent.created_at)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
