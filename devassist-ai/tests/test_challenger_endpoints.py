import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import datetime
from fastapi.testclient import TestClient
from api.main import app
from models.database import get_db_session
from models.entities import ProviderType, ReviewStatus, FindingSeverity

@pytest.fixture
def mock_db_session():
    session = MagicMock()
    session.execute = AsyncMock()
    return session

def test_list_repositories_endpoint(mock_db_session):
    """Verify that GET /api/v3/repositories returns correct metrics and format."""
    # Mock RepositoryRepo.get_all_active
    mock_repo = MagicMock()
    mock_repo.id = 1
    mock_repo.provider = ProviderType.GITHUB
    mock_repo.full_name = "owner/repo"
    mock_repo.is_active = True
    mock_repo.created_at = datetime.datetime(2026, 6, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # We need to mock session.execute calls.
    # list_repositories runs:
    # 1. total_stmt -> scalar_one_or_none() for total reviews
    # 2. completed_stmt -> scalar_one_or_none() for completed reviews
    # 3. open_issues_stmt -> scalar_one_or_none() for open issues
    
    mock_total_res = MagicMock()
    mock_total_res.scalar_one_or_none.return_value = 10  # 10 total reviews
    
    mock_completed_res = MagicMock()
    mock_completed_res.scalar_one_or_none.return_value = 8   # 8 completed reviews (80% success rate)
    
    mock_open_issues_res = MagicMock()
    mock_open_issues_res.scalar_one_or_none.return_value = 3  # 3 open issues

    # Configure side effect for session.execute
    mock_db_session.execute.side_effect = [mock_total_res, mock_completed_res, mock_open_issues_res]

    with patch("models.repositories.RepositoryRepo.get_all_active", new_callable=AsyncMock) as mock_get_all:
        mock_get_all.return_value = [mock_repo]
        
        app.dependency_overrides[get_db_session] = lambda: mock_db_session
        
        client = TestClient(app)
        response = client.get("/api/v3/repositories")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == 1
        assert data[0]["provider"] == "github"
        assert data[0]["full_name"] == "owner/repo"
        assert data[0]["is_active"] is True
        assert data[0]["reviews_count"] == 10
        assert data[0]["open_issues"] == 3
        assert data[0]["success_rate"] == 80
        
        app.dependency_overrides.clear()

def test_get_analytics_endpoint(mock_db_session):
    """Verify that GET /api/v3/analytics aggregates correctly."""
    # 1. review_stats_rows: status and cnt
    row1 = MagicMock()
    row1.status = ReviewStatus.COMPLETED
    row1.cnt = 5
    
    row2 = MagicMock()
    row2.status = ReviewStatus.FAILED
    row2.cnt = 2
    
    mock_review_res = MagicMock()
    mock_review_res.__iter__.return_value = [row1, row2]
    
    # 2. repo_count_result
    mock_repo_res = MagicMock()
    mock_repo_res.scalar_one_or_none.return_value = 4
    
    # 3. sev_rows
    sev1 = MagicMock()
    sev1.severity = FindingSeverity.ERROR
    sev1.cnt = 3
    
    sev2 = MagicMock()
    sev2.severity = FindingSeverity.WARNING
    sev2.cnt = 4
    
    mock_sev_res = MagicMock()
    mock_sev_res.__iter__.return_value = [sev1, sev2]
    
    # 4. cat_rows
    cat1 = MagicMock()
    cat1.category = MagicMock(value="security")
    cat1.cnt = 7
    
    mock_cat_res = MagicMock()
    mock_cat_res.__iter__.return_value = [cat1]
    
    mock_avg_duration_res = MagicMock()
    mock_avg_duration_res.scalar_one_or_none.return_value = 120.0

    mock_db_session.execute.side_effect = [
        mock_review_res,
        mock_repo_res,
        mock_sev_res,
        mock_cat_res,
        mock_avg_duration_res
    ]
    
    app.dependency_overrides[get_db_session] = lambda: mock_db_session
    
    client = TestClient(app)
    response = client.get("/api/v3/analytics")
    
    assert response.status_code == 200
    data = response.json()
    assert data["reviews"]["total"] == 7
    assert data["reviews"]["completed"] == 5
    assert data["reviews"]["failed"] == 2
    assert data["total_repositories"] == 4
    assert data["findings_by_severity"]["critical"] == 3  # error -> critical
    assert data["findings_by_severity"]["high"] == 4      # warning -> high
    assert data["total_findings"] == 7
    assert data["avg_findings_per_review"] == 1.4  # 7 total findings / 5 completed
    assert len(data["findings_by_category"]) == 1
    
    app.dependency_overrides.clear()

def test_get_trends_endpoint(mock_db_session):
    """Verify that GET /api/v3/analytics/trends filters and groups correctly."""
    # Trends endpoint groups by day, severity, and count
    trend1 = MagicMock()
    trend1.day = "2026-06-24"
    trend1.severity = FindingSeverity.ERROR
    trend1.cnt = 2
    
    trend2 = MagicMock()
    trend2.day = "2026-06-25"
    trend2.severity = FindingSeverity.WARNING
    trend2.cnt = 1
    
    mock_trends_res = MagicMock()
    mock_trends_res.all.return_value = [trend1, trend2]
    
    mock_db_session.execute.return_value = mock_trends_res
    
    app.dependency_overrides[get_db_session] = lambda: mock_db_session
    
    client = TestClient(app)
    response = client.get("/api/v3/analytics/trends")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 30  # Should return exactly 30 days
    # Verify the structure of each entry
    for entry in data:
        assert "date" in entry
        assert "critical" in entry
        assert "high" in entry
        assert "other" in entry
        if entry["date"] == "2026-06-24":
            assert entry["critical"] == 2
        elif entry["date"] == "2026-06-25":
            assert entry["high"] == 1
            
    app.dependency_overrides.clear()

def test_get_all_reviews_endpoint(mock_db_session):
    """Verify that GET /api/v3/reviews returns list with total_findings."""
    review1 = MagicMock()
    review1.id = 101
    review1.status = ReviewStatus.COMPLETED
    review1.raw_summary = "All good"
    review1.commit_sha = "abcdef123"
    review1.created_at = datetime.datetime(2026, 6, 25, 10, 0, 0, tzinfo=datetime.timezone.utc)
    review1.completed_at = datetime.datetime(2026, 6, 25, 10, 5, 0, tzinfo=datetime.timezone.utc)
    review1.total_findings = 5
    
    # Mock pull request and repository relationships
    pr = MagicMock()
    pr.title = "Add new feature"
    pr.provider_pr_id = 42
    
    repo = MagicMock()
    repo.full_name = "org/repo"
    repo.provider = ProviderType.GITHUB
    
    pr.repository = repo
    review1.pull_request = pr
    
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [review1]
    
    mock_db_session.execute.return_value = mock_res
    
    app.dependency_overrides[get_db_session] = lambda: mock_db_session
    
    client = TestClient(app)
    response = client.get("/api/v3/reviews")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 101
    assert data[0]["status"] == "completed"
    assert data[0]["summary"] == "All good"
    assert data[0]["total_findings"] == 5
    assert data[0]["pr_title"] == "Add new feature"
    assert data[0]["repo_name"] == "org/repo"
    assert data[0]["provider"] == "github"
    
    app.dependency_overrides.clear()
