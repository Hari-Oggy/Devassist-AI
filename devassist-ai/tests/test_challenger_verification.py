"""
Challenger Verification Test

Empirically verifies that all API endpoints (/api/v3/repositories,
/api/v3/analytics, /api/v3/analytics/trends, /api/v3/reviews)
return correct values using a mock database populated with known records.
"""

from __future__ import annotations

import datetime
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.main import app
from models.database import Base, get_db_session
from models.entities import (
    Finding,
    FindingCategory,
    FindingSeverity,
    ProviderType,
    PullRequest,
    Repository,
    Review,
    ReviewStatus,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def test_session():
    """Provide a fresh in-memory SQLite session per test."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with factory() as sess:
        yield sess

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_api_endpoints_correctness(test_session):
    # ── 1. Populating DB with controlled records ──────────────────────
    # A repo
    repo = Repository(
        provider=ProviderType.GITHUB,
        full_name="testowner/testrepo",
        provider_id=112233,
        default_branch="main",
        is_active=True,
        created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2),
    )
    test_session.add(repo)
    await test_session.flush()

    # A PR
    pr = PullRequest(
        repository_id=repo.id,
        provider_pr_id=42,
        title="Fix core bugs",
        state="open",
        created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1),
    )
    test_session.add(pr)
    await test_session.flush()

    # A Review (completed)
    review = Review(
        pull_request_id=pr.id,
        status=ReviewStatus.COMPLETED,
        mode="fast",
        total_findings=3,
        error_count=1,
        warning_count=2,
        duration_seconds=12.5,
        commit_sha="a1b2c3d4e5f6",
        created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2),
        completed_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1),
    )
    test_session.add(review)
    await test_session.flush()

    # Finding 1: Severity Error (corresponds to Critical in analytics)
    f1 = Finding(
        review_id=review.id,
        file_path="src/security.py",
        line_start=12,
        line_end=12,
        severity=FindingSeverity.ERROR,
        category=FindingCategory.SECURITY,
        message="SQL injection vulnerability",
        tool_source="bandit",
        is_suppressed=False,
    )
    # Finding 2: Severity Warning (corresponds to High in analytics)
    f2 = Finding(
        review_id=review.id,
        file_path="src/utils.py",
        line_start=45,
        line_end=45,
        severity=FindingSeverity.WARNING,
        category=FindingCategory.CORRECTNESS,
        message="Unused variable warning",
        tool_source="ruff",
        is_suppressed=False,
    )
    # Finding 3: Severity Note (corresponds to Medium in analytics)
    f3 = Finding(
        review_id=review.id,
        file_path="src/main.py",
        line_start=90,
        line_end=90,
        severity=FindingSeverity.NOTE,
        category=FindingCategory.STYLE,
        message="Trailing whitespaces",
        tool_source="pylint",
        is_suppressed=False,
    )
    test_session.add_all([f1, f2, f3])
    await test_session.commit()

    # ── 2. Override FastAPI get_db_session ────────────────────────────
    app.dependency_overrides[get_db_session] = lambda: test_session

    client = TestClient(app)

    try:
        # ── 3. Test GET /api/v3/repositories ─────────────────────────
        res_repos = client.get("/api/v3/repositories")
        assert res_repos.status_code == 200
        repos_data = res_repos.json()
        assert len(repos_data) == 1
        assert repos_data[0]["full_name"] == "testowner/testrepo"
        assert repos_data[0]["reviews_count"] == 1
        assert repos_data[0]["open_issues"] == 3
        assert repos_data[0]["success_rate"] == 100

        # ── 4. Test GET /api/v3/analytics ────────────────────────────
        res_analytics = client.get("/api/v3/analytics")
        assert res_analytics.status_code == 200
        analytics_data = res_analytics.json()
        
        # Check review stats
        assert analytics_data["reviews"]["total"] == 1
        assert analytics_data["reviews"]["completed"] == 1
        assert analytics_data["reviews"]["failed"] == 0
        assert analytics_data["reviews"]["running"] == 0
        
        # Check severity breakdown mapping
        assert analytics_data["findings_by_severity"]["critical"] == 1  # FindingSeverity.ERROR
        assert analytics_data["findings_by_severity"]["high"] == 1      # FindingSeverity.WARNING
        assert analytics_data["findings_by_severity"]["medium"] == 1    # FindingSeverity.NOTE
        assert analytics_data["findings_by_severity"]["low"] == 0
        assert analytics_data["total_findings"] == 3
        assert analytics_data["total_repositories"] == 1
        assert analytics_data["avg_findings_per_review"] == 3.0

        # Check category breakdown
        categories = {cat["name"]: cat["count"] for cat in analytics_data["findings_by_category"]}
        assert categories.get("security") == 1
        assert categories.get("correctness") == 1
        assert categories.get("style") == 1

        # ── 5. Test GET /api/v3/analytics/trends ─────────────────────
        res_trends = client.get("/api/v3/analytics/trends")
        assert res_trends.status_code == 200
        trends_data = res_trends.json()
        assert len(trends_data) == 30
        
        # Find non-zero day in trend
        trend_days_with_issues = [t for t in trends_data if t["critical"] > 0 or t["high"] > 0 or t["other"] > 0]
        assert len(trend_days_with_issues) == 1
        day_issue = trend_days_with_issues[0]
        assert day_issue["critical"] == 1
        assert day_issue["high"] == 1
        assert day_issue["other"] == 1

        # ── 6. Test GET /api/v3/reviews ──────────────────────────────
        res_reviews = client.get("/api/v3/reviews")
        assert res_reviews.status_code == 200
        reviews_data = res_reviews.json()
        assert len(reviews_data) == 1
        assert reviews_data[0]["id"] == review.id
        assert reviews_data[0]["status"] == ReviewStatus.COMPLETED.value
        assert reviews_data[0]["total_findings"] == 3
        assert reviews_data[0]["commit_sha"] == "a1b2c3d4e5f6"

    finally:
        app.dependency_overrides.clear()
