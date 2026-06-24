import pytest
from unittest.mock import patch, MagicMock
import datetime
from fastapi.testclient import TestClient
from api.main import app
from models.database import get_db_session
from models.entities import ProviderType

@pytest.fixture
def mock_db_session():
    return MagicMock()

def test_post_repositories_valid_clone(mock_db_session):
    """Test POST /api/v3/repositories with a valid repository clone scenario."""
    with patch("codegraph.repo_cloner.RepoCloner") as MockCloner, \
         patch("models.repositories.RepositoryRepo.upsert") as mock_upsert:
        
        cloner_instance = MockCloner.return_value
        cloner_instance.get_repo_path.return_value = "/mock/repo/path"
        cloner_instance.__enter__.return_value = cloner_instance
        
        mock_repo = MagicMock()
        mock_repo.id = 456
        mock_repo.provider = ProviderType.GITHUB
        mock_repo.full_name = "valid/repo"
        mock_repo.is_active = True
        mock_repo.created_at = datetime.datetime.now(datetime.timezone.utc)
        mock_upsert.return_value = mock_repo
        
        app.dependency_overrides[get_db_session] = lambda: mock_db_session
        
        client = TestClient(app)
        response = client.post(
            "/api/v3/repositories",
            json={
                "provider": "github",
                "full_name": "valid/repo",
                "default_branch": "main"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 456
        assert data["full_name"] == "valid/repo"
        assert data["is_active"] is True
        
        MockCloner.assert_called_once()
        cloner_instance.get_repo_path.assert_called_once()
        
        app.dependency_overrides.clear()

def test_post_repositories_invalid_clone_runtime_error(mock_db_session):
    """Test POST /api/v3/repositories handles cloner RuntimeError properly (returns 400)."""
    with patch("codegraph.repo_cloner.RepoCloner") as MockCloner:
        
        cloner_instance = MockCloner.return_value
        cloner_instance.get_repo_path.side_effect = RuntimeError("Mock git clone failed")
        cloner_instance.__enter__.return_value = cloner_instance
        
        app.dependency_overrides[get_db_session] = lambda: mock_db_session
        
        client = TestClient(app)
        response = client.post(
            "/api/v3/repositories",
            json={
                "provider": "github",
                "full_name": "invalid/repo",
                "default_branch": "main"
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "Failed to clone repository" in data["detail"]
        assert "Mock git clone failed" in data["detail"]
        
        app.dependency_overrides.clear()

def test_post_repositories_invalid_clone_value_error(mock_db_session):
    """Test POST /api/v3/repositories handles cloner ValueError properly (returns 400)."""
    with patch("codegraph.repo_cloner.RepoCloner") as MockCloner:
        
        cloner_instance = MockCloner.return_value
        cloner_instance.get_repo_path.side_effect = ValueError("Mock invalid repo configuration")
        cloner_instance.__enter__.return_value = cloner_instance
        
        app.dependency_overrides[get_db_session] = lambda: mock_db_session
        
        client = TestClient(app)
        response = client.post(
            "/api/v3/repositories",
            json={
                "provider": "gitlab",
                "full_name": "invalid-config/repo",
                "default_branch": "develop"
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "Failed to clone repository" in data["detail"]
        assert "Mock invalid repo configuration" in data["detail"]
        
        app.dependency_overrides.clear()

def test_post_repositories_invalid_payload(mock_db_session):
    """Test POST /api/v3/repositories with an invalid payload structure (returns 422)."""
    app.dependency_overrides[get_db_session] = lambda: mock_db_session
    
    client = TestClient(app)
    # Sending invalid provider type
    response = client.post(
        "/api/v3/repositories",
        json={
            "provider": "bitbucket",
            "full_name": "owner/repo",
            "default_branch": "main"
        }
    )
    
    assert response.status_code == 422
    app.dependency_overrides.clear()
