"""
Tests for Phase 5: PostgreSQL ORM entities and repository layer.

All tests use an in-memory SQLite database so no live PostgreSQL instance
is needed. SQLAlchemy's async aiosqlite driver is used.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# ── Test DB setup ──────────────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def session():
    """Provide a fresh in-memory SQLite session per test."""
    from models.database import Base
    from models import entities  # noqa: F401 — register models

    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with factory() as sess:
        yield sess

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── Entity import tests ────────────────────────────────────────────────

class TestEntityImports:
    def test_all_entities_importable(self):
        from models.entities import (
            Repository, PullRequest, Review, Finding, ReviewEvent,
            ProviderType, ReviewStatus, FindingSeverity, FindingCategory, EventType,
        )
        assert Repository.__tablename__ == "repositories"
        assert PullRequest.__tablename__ == "pull_requests"
        assert Review.__tablename__ == "reviews"
        assert Finding.__tablename__ == "findings"
        assert ReviewEvent.__tablename__ == "review_events"

    def test_enums_have_expected_values(self):
        from models.entities import ProviderType, ReviewStatus, FindingSeverity

        assert ProviderType.GITHUB == "github"
        assert ProviderType.GITLAB == "gitlab"
        assert ReviewStatus.PENDING == "pending"
        assert ReviewStatus.COMPLETED == "completed"
        assert FindingSeverity.ERROR == "error"
        assert FindingSeverity.WARNING == "warning"


# ── RepositoryRepo ─────────────────────────────────────────────────────

class TestRepositoryRepo:
    @pytest.mark.asyncio
    async def test_upsert_creates_new(self, session):
        from models.repositories import RepositoryRepo
        repo = await RepositoryRepo.upsert(session, "github", "owner/repo")
        await session.commit()
        assert repo.id is not None
        assert repo.full_name == "owner/repo"
        assert repo.provider == "github"
        assert repo.is_active is True

    @pytest.mark.asyncio
    async def test_upsert_returns_existing(self, session):
        from models.repositories import RepositoryRepo
        r1 = await RepositoryRepo.upsert(session, "github", "owner/repo")
        await session.flush()
        r2 = await RepositoryRepo.upsert(session, "github", "owner/repo")
        assert r1.id == r2.id

    @pytest.mark.asyncio
    async def test_get_by_full_name(self, session):
        from models.repositories import RepositoryRepo
        await RepositoryRepo.upsert(session, "gitlab", "group/project")
        await session.flush()
        found = await RepositoryRepo.get_by_full_name(session, "gitlab", "group/project")
        assert found is not None
        assert found.full_name == "group/project"

    @pytest.mark.asyncio
    async def test_get_by_full_name_not_found(self, session):
        from models.repositories import RepositoryRepo
        result = await RepositoryRepo.get_by_full_name(session, "github", "nonexistent/repo")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_active(self, session):
        from models.repositories import RepositoryRepo
        await RepositoryRepo.upsert(session, "github", "a/b")
        await RepositoryRepo.upsert(session, "github", "c/d")
        await session.flush()
        active = await RepositoryRepo.get_all_active(session)
        assert len(active) >= 2

    @pytest.mark.asyncio
    async def test_deactivate(self, session):
        from models.repositories import RepositoryRepo
        repo = await RepositoryRepo.upsert(session, "github", "x/y")
        await session.flush()
        result = await RepositoryRepo.deactivate(session, repo.id)
        await session.flush()
        assert result is True
        refreshed = await RepositoryRepo.get_by_id(session, repo.id)
        assert refreshed.is_active is False


# ── PullRequestRepo ────────────────────────────────────────────────────

class TestPullRequestRepo:
    @pytest.mark.asyncio
    async def test_upsert_creates_pr(self, session):
        from models.repositories import RepositoryRepo, PullRequestRepo
        repo = await RepositoryRepo.upsert(session, "github", "o/r")
        await session.flush()
        pr = await PullRequestRepo.upsert(
            session, repo.id, 42,
            title="Add feature X",
            source_branch="feature/x",
            target_branch="main",
        )
        await session.flush()
        assert pr.id is not None
        assert pr.provider_pr_id == 42
        assert pr.title == "Add feature X"

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, session):
        from models.repositories import RepositoryRepo, PullRequestRepo
        repo = await RepositoryRepo.upsert(session, "github", "o/r2")
        await session.flush()
        pr1 = await PullRequestRepo.upsert(session, repo.id, 1, title="Old title")
        await session.flush()
        pr2 = await PullRequestRepo.upsert(session, repo.id, 1, title="New title")
        assert pr1.id == pr2.id
        assert pr2.title == "New title"

    @pytest.mark.asyncio
    async def test_list_open(self, session):
        from models.repositories import RepositoryRepo, PullRequestRepo
        repo = await RepositoryRepo.upsert(session, "github", "o/r3")
        await session.flush()
        await PullRequestRepo.upsert(session, repo.id, 1, state="open")
        await PullRequestRepo.upsert(session, repo.id, 2, state="closed")
        await session.flush()
        open_prs = await PullRequestRepo.list_open(session, repo.id)
        assert len(open_prs) == 1
        assert open_prs[0].provider_pr_id == 1


# ── ReviewRepo ─────────────────────────────────────────────────────────

class TestReviewRepo:
    @pytest_asyncio.fixture
    async def pr_id(self, session):
        from models.repositories import RepositoryRepo, PullRequestRepo
        repo = await RepositoryRepo.upsert(session, "github", "rev/test")
        await session.flush()
        pr = await PullRequestRepo.upsert(session, repo.id, 99)
        await session.flush()
        return pr.id

    @pytest.mark.asyncio
    async def test_create_review(self, session, pr_id):
        from models.repositories import ReviewRepo
        from models.entities import ReviewStatus
        review = await ReviewRepo.create(session, pr_id, mode="fast", commit_sha="abc123")
        await session.flush()
        assert review.id is not None
        assert review.status == ReviewStatus.PENDING
        assert review.mode == "fast"
        assert review.commit_sha == "abc123"

    @pytest.mark.asyncio
    async def test_mark_running(self, session, pr_id):
        from models.repositories import ReviewRepo
        from models.entities import ReviewStatus
        review = await ReviewRepo.create(session, pr_id)
        await session.flush()
        await ReviewRepo.mark_running(session, review.id)
        await session.flush()
        updated = await ReviewRepo.get_by_id(session, review.id)
        assert updated.status == ReviewStatus.RUNNING

    @pytest.mark.asyncio
    async def test_mark_completed(self, session, pr_id):
        from models.repositories import ReviewRepo
        from models.entities import ReviewStatus
        review = await ReviewRepo.create(session, pr_id)
        await session.flush()
        await ReviewRepo.mark_completed(
            session, review.id,
            total_findings=5, error_count=2, warning_count=3,
            duration_seconds=12.5,
        )
        await session.flush()
        updated = await ReviewRepo.get_by_id(session, review.id)
        assert updated.status == ReviewStatus.COMPLETED
        assert updated.total_findings == 5
        assert updated.error_count == 2
        assert updated.completed_at is not None

    @pytest.mark.asyncio
    async def test_mark_failed(self, session, pr_id):
        from models.repositories import ReviewRepo
        from models.entities import ReviewStatus
        review = await ReviewRepo.create(session, pr_id)
        await session.flush()
        await ReviewRepo.mark_failed(session, review.id, "LLM quota exceeded")
        await session.flush()
        updated = await ReviewRepo.get_by_id(session, review.id)
        assert updated.status == ReviewStatus.FAILED
        assert "quota" in updated.error_message

    @pytest.mark.asyncio
    async def test_list_for_pr(self, session, pr_id):
        from models.repositories import ReviewRepo
        await ReviewRepo.create(session, pr_id)
        await ReviewRepo.create(session, pr_id)
        await session.flush()
        reviews = await ReviewRepo.list_for_pr(session, pr_id)
        assert len(reviews) == 2


# ── FindingRepo ────────────────────────────────────────────────────────

class TestFindingRepo:
    @pytest_asyncio.fixture
    async def review_id(self, session):
        from models.repositories import RepositoryRepo, PullRequestRepo, ReviewRepo
        repo = await RepositoryRepo.upsert(session, "github", "find/test")
        await session.flush()
        pr = await PullRequestRepo.upsert(session, repo.id, 7)
        await session.flush()
        review = await ReviewRepo.create(session, pr.id)
        await session.flush()
        return review.id

    @pytest.mark.asyncio
    async def test_bulk_create(self, session, review_id):
        from models.repositories import FindingRepo
        findings = [
            {"file_path": "auth.py", "line_start": 10, "severity": "error",
             "message": "SQL injection risk", "tool_source": "bandit", "category": "security"},
            {"file_path": "utils.py", "line_start": 42, "severity": "warning",
             "message": "Unused variable", "tool_source": "ruff", "category": "style"},
        ]
        created = await FindingRepo.bulk_create(session, review_id, findings)
        await session.flush()
        assert len(created) == 2
        assert created[0].file_path == "auth.py"

    @pytest.mark.asyncio
    async def test_list_for_review(self, session, review_id):
        from models.repositories import FindingRepo
        await FindingRepo.bulk_create(session, review_id, [
            {"file_path": "a.py", "severity": "error", "message": "issue"},
        ])
        await session.flush()
        listed = await FindingRepo.list_for_review(session, review_id)
        assert len(listed) == 1

    @pytest.mark.asyncio
    async def test_suppress(self, session, review_id):
        from models.repositories import FindingRepo
        [f] = await FindingRepo.bulk_create(session, review_id, [
            {"file_path": "x.py", "severity": "warning", "message": "minor issue"},
        ])
        await session.flush()
        result = await FindingRepo.suppress(session, f.id, "False positive — test code")
        await session.flush()
        assert result is True
        listed = await FindingRepo.list_for_review(session, review_id)
        assert listed[0].is_suppressed is True
        assert "False positive" in listed[0].suppression_reason


# ── ReviewEventRepo ────────────────────────────────────────────────────

class TestReviewEventRepo:
    @pytest_asyncio.fixture
    async def review_id(self, session):
        from models.repositories import RepositoryRepo, PullRequestRepo, ReviewRepo
        repo = await RepositoryRepo.upsert(session, "github", "event/test")
        await session.flush()
        pr = await PullRequestRepo.upsert(session, repo.id, 5)
        await session.flush()
        review = await ReviewRepo.create(session, pr.id)
        await session.flush()
        return review.id

    @pytest.mark.asyncio
    async def test_create_event(self, session, review_id):
        from models.repositories import ReviewEventRepo
        event = await ReviewEventRepo.create(
            session, review_id,
            event_type="review_started",
            message="Review kicked off",
            data={"mode": "ensemble"},
        )
        await session.flush()
        assert event.id is not None
        assert event.event_type == "review_started"
        assert event.data["mode"] == "ensemble"

    @pytest.mark.asyncio
    async def test_list_for_review(self, session, review_id):
        from models.repositories import ReviewEventRepo
        await ReviewEventRepo.create(session, review_id, "review_started", "started")
        await ReviewEventRepo.create(session, review_id, "review_completed", "done")
        await session.flush()
        events = await ReviewEventRepo.list_for_review(session, review_id)
        assert len(events) == 2
        assert events[0].event_type == "review_started"
