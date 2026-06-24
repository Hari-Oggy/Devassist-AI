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

def test_create_repository_clone_success(mock_db_session):
    with patch("codegraph.repo_cloner.RepoCloner") as MockCloner, \
         patch("models.repositories.RepositoryRepo.upsert") as mock_upsert:
        
        cloner_instance = MockCloner.return_value
        cloner_instance.get_repo_path.return_value = "/mock/repo/path"
        cloner_instance.__enter__.return_value = cloner_instance
        
        mock_repo = MagicMock()
        mock_repo.id = 123
        mock_repo.provider = ProviderType.GITHUB
        mock_repo.full_name = "owner/repo"
        mock_repo.is_active = True
        mock_repo.created_at = datetime.datetime.now(datetime.timezone.utc)
        mock_upsert.return_value = mock_repo
        
        app.dependency_overrides[get_db_session] = lambda: mock_db_session
        
        client = TestClient(app)
        response = client.post(
            "/api/v3/repositories",
            json={
                "provider": "github",
                "full_name": "owner/repo",
                "default_branch": "main"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 123
        assert data["full_name"] == "owner/repo"
        
        MockCloner.assert_called_once()
        cloner_instance.get_repo_path.assert_called_once()
        
        app.dependency_overrides.clear()

def test_create_repository_clone_failure(mock_db_session):
    with patch("codegraph.repo_cloner.RepoCloner") as MockCloner:
        
        cloner_instance = MockCloner.return_value
        cloner_instance.get_repo_path.side_effect = RuntimeError("Git clone failed")
        cloner_instance.__enter__.return_value = cloner_instance
        
        app.dependency_overrides[get_db_session] = lambda: mock_db_session
        
        client = TestClient(app)
        response = client.post(
            "/api/v3/repositories",
            json={
                "provider": "github",
                "full_name": "owner/repo",
                "default_branch": "main"
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "Failed to clone repository" in data["detail"]
        
        app.dependency_overrides.clear()
