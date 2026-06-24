import os
import importlib
import asyncio
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app
from models.database import get_db_session
from models.entities import ProviderType

# ── 1. DATABASE URL SETUP VERIFICATION ────────────────────────────────

def test_database_url_normalization():
    """Verify that models/database.py correctly normalises PostgreSQL connection URLs."""
    import models.database
    
    # Test case: postgresql://
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost:5432/db"}):
        importlib.reload(models.database)
        assert models.database._DATABASE_URL == "postgresql+asyncpg://user:pass@localhost:5432/db"
        
    # Test case: postgres:// (Heroku style)
    with patch.dict(os.environ, {"DATABASE_URL": "postgres://user:pass@localhost:5432/db"}):
        importlib.reload(models.database)
        assert models.database._DATABASE_URL == "postgresql+asyncpg://user:pass@localhost:5432/db"
        
    # Test case: already correct postgresql+asyncpg://
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db"}):
        importlib.reload(models.database)
        assert models.database._DATABASE_URL == "postgresql+asyncpg://user:pass@localhost:5432/db"
        
    # Test case: non-postgresql URL remains untouched
    with patch.dict(os.environ, {"DATABASE_URL": "sqlite+aiosqlite:///:memory:"}):
        importlib.reload(models.database)
        assert models.database._DATABASE_URL == "sqlite+aiosqlite:///:memory:"
        
    # Restore standard environment settings for other tests
    importlib.reload(models.database)


# ── 2. SSE GENERATOR CONSUMPTION VERIFICATION ─────────────────────────

@pytest.mark.asyncio
async def test_sse_happy_path():
    """Verify standard SSE flow: connected handshake, published finding, and auto-termination on completion."""
    from api.sse import sse_manager
    review_id = 1001
    
    generator = sse_manager.subscribe(review_id, timeout_seconds=1.0)
    
    # First chunk must be the connected handshake
    first_chunk = await generator.__anext__()
    assert "event: connected" in first_chunk
    assert "SSE stream connected" in first_chunk
    
    # Publish finding
    await sse_manager.publish_finding(
        review_id=review_id,
        file_path="src/auth.py",
        line=42,
        severity="warning",
        message="Use of MD5 is insecure"
    )
    
    second_chunk = await generator.__anext__()
    assert "event: finding_added" in second_chunk
    assert "Use of MD5 is insecure" in second_chunk
    assert "src/auth.py" in second_chunk
    
    # Publish completion (terminal event)
    await sse_manager.publish_review_completed(
        review_id=review_id,
        findings_count=1,
        duration_seconds=3.5
    )
    
    third_chunk = await generator.__anext__()
    assert "event: review_completed" in third_chunk
    assert "findings_count" in third_chunk
    
    # Stream should self-terminate now
    with pytest.raises(StopAsyncIteration):
        await generator.__anext__()


@pytest.mark.asyncio
async def test_sse_failed_terminal():
    """Verify that SSE stream self-terminates on review_failed terminal event."""
    from api.sse import sse_manager
    review_id = 1002
    
    generator = sse_manager.subscribe(review_id, timeout_seconds=1.0)
    
    # handshake
    await generator.__anext__()
    
    # Publish failure (terminal event)
    await sse_manager.publish_review_failed(
        review_id=review_id,
        error="LLM API connection timed out"
    )
    
    failed_chunk = await generator.__anext__()
    assert "event: review_failed" in failed_chunk
    assert "LLM API connection timed out" in failed_chunk
    
    # Stream should self-terminate now
    with pytest.raises(StopAsyncIteration):
        await generator.__anext__()


@pytest.mark.asyncio
async def test_sse_keepalive():
    """Verify that SSE stream periodically emits keepalive heartbeats if no events are published."""
    from api.sse import sse_manager
    review_id = 1003
    
    # Set a very low timeout to trigger keepalive quickly
    generator = sse_manager.subscribe(review_id, timeout_seconds=0.02)
    
    # handshake
    await generator.__anext__()
    
    # Next yields should be keepalive lines due to timeout
    keepalive_1 = await generator.__anext__()
    assert keepalive_1 == ": keepalive\n\n"
    
    keepalive_2 = await generator.__anext__()
    assert keepalive_2 == ": keepalive\n\n"
    
    # Clean closure
    await generator.aclose()


# ── 3. REPOSITORY CLONE VALIDATION ENDPOINT VERIFICATION ──────────────

@pytest.fixture
def mock_db():
    return MagicMock()

def test_api_repository_clone_url_construction_github_no_token(mock_db):
    """Verify GITHUB repository clone endpoint URL construction when no token is configured."""
    from core.config import Settings
    custom_settings = Settings()
    custom_settings.GITHUB_TOKEN = None
    
    with patch("core.config.get_settings", return_value=custom_settings), \
         patch.dict(os.environ, {"GITHUB_TOKEN": ""}), \
         patch("codegraph.repo_cloner.RepoCloner") as MockCloner, \
         patch("models.repositories.RepositoryRepo.upsert") as mock_upsert:
        
        mock_upsert.return_value = MagicMock(id=1, provider=ProviderType.GITHUB, full_name="user/repo", is_active=True)
        
        app.dependency_overrides[get_db_session] = lambda: mock_db
        client = TestClient(app)
        
        response = client.post(
            "/api/v3/repositories",
            json={"provider": "github", "full_name": "user/repo"}
        )
        assert response.status_code == 200
        
        # Verify RepoCloner was called with correct public HTTPS URL
        MockCloner.assert_called_once_with(repo_url="https://github.com/user/repo.git")
        app.dependency_overrides.clear()


def test_api_repository_clone_url_construction_github_with_token(mock_db):
    """Verify GITHUB repository clone endpoint URL construction with an access token."""
    from core.config import Settings
    custom_settings = Settings()
    custom_settings.GITHUB_TOKEN = "ghp_mocktesttoken123"
    
    with patch("core.config.get_settings", return_value=custom_settings), \
         patch("codegraph.repo_cloner.RepoCloner") as MockCloner, \
         patch("models.repositories.RepositoryRepo.upsert") as mock_upsert:
        
        mock_upsert.return_value = MagicMock(id=2, provider=ProviderType.GITHUB, full_name="user/repo", is_active=True)
        
        app.dependency_overrides[get_db_session] = lambda: mock_db
        client = TestClient(app)
        
        response = client.post(
            "/api/v3/repositories",
            json={"provider": "github", "full_name": "user/repo"}
        )
        assert response.status_code == 200
        
        # Verify RepoCloner was called with correct authenticated HTTPS URL
        MockCloner.assert_called_once_with(repo_url="https://x-access-token:ghp_mocktesttoken123@github.com/user/repo.git")
        app.dependency_overrides.clear()


def test_api_repository_clone_url_construction_gitlab_with_token(mock_db):
    """Verify GITLAB repository clone endpoint URL construction with custom host and token."""
    from core.config import Settings
    custom_settings = Settings()
    custom_settings.GITLAB_TOKEN = "glpat-mocktoken"
    custom_settings.GITLAB_API_URL = "https://gitlab.custom.domain/api/v4"
    
    with patch("core.config.get_settings", return_value=custom_settings), \
         patch("codegraph.repo_cloner.RepoCloner") as MockCloner, \
         patch("models.repositories.RepositoryRepo.upsert") as mock_upsert:
        
        mock_upsert.return_value = MagicMock(id=3, provider=ProviderType.GITLAB, full_name="group/subgroup/project", is_active=True)
        
        app.dependency_overrides[get_db_session] = lambda: mock_db
        client = TestClient(app)
        
        response = client.post(
            "/api/v3/repositories",
            json={"provider": "gitlab", "full_name": "group/subgroup/project"}
        )
        assert response.status_code == 200
        
        # Verify RepoCloner was called with custom gitlab host and oauth2 auth
        MockCloner.assert_called_once_with(repo_url="https://oauth2:glpat-mocktoken@gitlab.custom.domain/group/subgroup/project.git")
        app.dependency_overrides.clear()
