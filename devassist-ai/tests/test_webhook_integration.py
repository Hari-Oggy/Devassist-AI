import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from api.main import app

def test_webhook_triggers_review_with_correct_context():
    # Setup test payload
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "title": "Fix bug",
            "user": {
                "login": "testuser",
                "type": "User"
            },
            "head": {
                "ref": "feature-branch",
                "sha": "abcdef123456"
            },
            "base": {
                "ref": "main"
            },
            "draft": False,
            "html_url": "https://github.com/testowner/testrepo/pull/42"
        },
        "repository": {
            "full_name": "testowner/testrepo",
            "id": 123456
        }
    }

    # Mock the Celery task delay method
    with patch("workers.review_worker.run_review.delay") as mock_delay:
        mock_task = MagicMock()
        mock_task.id = "mock-task-id-123"
        mock_delay.return_value = mock_task

        client = TestClient(app)
        headers = {
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=mocksignature"
        }

        # Mock _verify_signature to always return True for testing
        with patch("api.webhook._verify_signature", return_value=True):
            response = client.post("/api/v3/github/webhook", json=payload, headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "review_triggered"
        assert data["pr_number"] == 42

        # Verify delay was called once
        mock_delay.assert_called_once()
        
        # Extract the context dict passed to delay
        context = mock_delay.call_args[0][0]
        
        # Verify all expected keys exist and have correct values
        assert context["provider"] == "github"
        assert context["project_path"] == "testowner/testrepo"
        assert context["project_id"] == 123456
        assert context["pr_number"] == 42
        assert context["mr_title"] == "Fix bug"
        assert context["mr_author"] == "testuser"
        assert context["source_branch"] == "feature-branch"
        assert context["target_branch"] == "main"
        assert context["is_draft"] is False
        assert context["mr_url"] == "https://github.com/testowner/testrepo/pull/42"
        assert context["last_commit_sha"] == "abcdef123456"

@pytest.mark.asyncio
async def test_worker_parses_context_correctly():
    from workers.review_worker import _run_review_async
    from models.entities import ProviderType

    # Prepare context dictionary that mimics webhook output
    context = {
        "provider": "github",
        "project_path": "testowner/testrepo",
        "project_id": 123456,
        "pr_number": 42,
        "mr_title": "Fix bug",
        "mr_author": "testuser",
        "source_branch": "feature-branch",
        "target_branch": "main",
        "is_draft": False,
        "mr_url": "https://github.com/testowner/testrepo/pull/42",
        "last_commit_sha": "abcdef123456"
    }

    # Mock all DB repositories and helper classes in workers.review_worker
    mock_session = AsyncMock()
    
    mock_repo = MagicMock()
    mock_repo.id = 100
    mock_repo.provider = ProviderType.GITHUB
    mock_repo.full_name = "testowner/testrepo"

    mock_pr = MagicMock()
    mock_pr.id = 200

    mock_review = MagicMock()
    mock_review.id = 300

    # Create mock sse_manager with AsyncMock methods
    mock_sse = MagicMock()
    mock_sse.publish_review_started = AsyncMock()
    mock_sse.publish_review_completed = AsyncMock()
    mock_sse.publish_review_failed = AsyncMock()

    # Patch database context manager and repository methods
    with patch("workers.review_worker.get_db_session_context") as mock_db_ctx, \
         patch("models.repositories.RepositoryRepo.upsert", new_callable=AsyncMock) as mock_repo_upsert, \
         patch("models.repositories.PullRequestRepo.upsert", new_callable=AsyncMock) as mock_pr_upsert, \
         patch("models.repositories.ReviewRepo.create", new_callable=AsyncMock) as mock_review_create, \
         patch("models.repositories.ReviewRepo.mark_running", new_callable=AsyncMock) as mock_review_running, \
         patch("models.repositories.ReviewRepo.mark_completed", new_callable=AsyncMock) as mock_review_completed, \
         patch("models.repositories.ReviewEventRepo.create", new_callable=AsyncMock) as mock_event_create, \
         patch("workers.review_worker.sse_manager", mock_sse), \
         patch("agents.tools.github_tool.get_github_client") as mock_gh_client, \
         patch("workers.review_worker.load_prompt") as mock_load_prompt, \
         patch("workers.review_worker.ReviewPipeline") as mock_pipeline_cls, \
         patch("workers.review_worker.RepoCloner") as mock_cloner_cls, \
         patch("workers.review_worker.CodeGraphBuilder") as mock_builder_cls, \
         patch("workers.review_worker.ImpactAnalyzer") as mock_analyzer_cls, \
         patch("models.repositories.FindingRepo.bulk_create", new_callable=AsyncMock) as mock_finding_bulk_create:

        # Database session context manager mock setup
        mock_db_ctx.return_value.__aenter__.return_value = mock_session
        
        # Setup repository upsert / create return values
        mock_repo_upsert.return_value = mock_repo
        mock_pr_upsert.return_value = mock_pr
        mock_review_create.return_value = mock_review

        # Setup GitHub client mock
        mock_file = MagicMock()
        mock_file.filename = "src/main.py"
        mock_file.patch = "@@ -1,3 +1,3 @@"
        mock_file.status = "modified"
        mock_file.additions = 1
        mock_file.deletions = 1

        mock_gh = MagicMock()
        mock_gh.repo.get_pull.return_value.get_files.return_value = [mock_file]
        mock_gh_client.return_value = mock_gh

        # Setup Pipeline and CodeGraph mocks
        mock_pipeline = mock_pipeline_cls.return_value
        mock_run_result = MagicMock()
        mock_run_result.findings = []
        mock_run_result.total_tokens_input = 100
        mock_run_result.total_tokens_output = 50
        mock_run_result.total_cost_estimate = 0.01
        mock_run_result.duration_seconds = 1.5
        mock_run_result.model_used = "mock-gpt"
        mock_run_result.provider_used = "mock-provider"
        mock_run_result.distillation.summary = "Distillation summary"
        mock_pipeline.run.return_value = mock_run_result

        # Cloner, Graph builder, and analyzer mocks
        mock_cloner = mock_cloner_cls.return_value
        mock_cloner.get_repo_path.return_value = "/mock/repo"
        mock_cloner.__enter__.return_value = mock_cloner
        
        mock_builder = mock_builder_cls.return_value
        mock_builder.build.return_value = MagicMock()

        mock_analyzer = mock_analyzer_cls.return_value
        mock_report = MagicMock()
        mock_report.to_dict.return_value = {"impact": "low"}
        mock_analyzer.analyze.return_value = mock_report

        # Execute _run_review_async
        result = await _run_review_async(context)

        # Assert correct argument passing & parsing for database entity updates
        mock_repo_upsert.assert_called_once_with(
            session=mock_session,
            provider=ProviderType.GITHUB,
            full_name="testowner/testrepo",
            provider_id=123456
        )

        mock_pr_upsert.assert_called_once_with(
            session=mock_session,
            repository_id=100,
            provider_pr_id=42,
            title="Fix bug",
            author="testuser",
            source_branch="feature-branch",
            target_branch="main",
            is_draft=False,
            provider_url="https://github.com/testowner/testrepo/pull/42"
        )

        from core.pipeline_config import get_pipeline_settings
        mock_review_create.assert_called_once_with(
            session=mock_session,
            pull_request_id=200,
            mode=get_pipeline_settings().REVIEW_MODE,
            commit_sha="abcdef123456"
        )

        mock_review_running.assert_called_once_with(mock_session, 300)

        # Assert GitHub client was queried with correct PR number
        assert mock_gh.repo.get_pull.call_count == 2
        mock_gh.repo.get_pull.assert_any_call(42)

        # Assert review was successfully completed
        assert result["success"] is True
        assert result["findings_count"] == 0
