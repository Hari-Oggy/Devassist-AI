import pytest
from unittest.mock import patch, MagicMock
from agents.review_agent import ReviewAgent

@pytest.fixture
def mock_dependencies():
    with patch("agents.review_agent.get_settings") as mock_settings, \
         patch("agents.review_agent.LLMRouter") as mock_router, \
         patch("agents.review_agent.CodebaseRetriever") as mock_retriever, \
         patch("agents.review_agent.get_github_client") as mock_gh_client:
         
        settings_instance = MagicMock()
        settings_instance.LLM_PROVIDER = "openai"
        mock_settings.return_value = settings_instance
        
        gh_instance = MagicMock()
        mock_gh_client.return_value = gh_instance
        
        router_instance = MagicMock()
        mock_router.return_value = router_instance
        
        retriever_instance = MagicMock()
        mock_retriever.return_value = retriever_instance
        
        yield {
            "settings": settings_instance,
            "router": router_instance,
            "retriever": retriever_instance,
            "gh_client": gh_instance
        }

def test_review_single_file_success(mock_dependencies):
    router = mock_dependencies["router"]
    
    # Mock successful LLM response
    mock_response = MagicMock()
    mock_response.success = True
    mock_response.content = '{"comments": [{"line": 10, "message": "Test comment", "category": "style"}]}'
    mock_response.provider = "openai"
    mock_response.model = "gpt-4o"
    mock_response.tokens_input = 100
    mock_response.tokens_output = 50
    mock_response.latency = 1.0
    router.generate.return_value = mock_response
    
    agent = ReviewAgent(repo_name="test/repo")
    
    file_data = {
        "filename": "test.py",
        "patch": "@@ -1,5 +1,5 @@\n+print('test')",
        "status": "modified",
        "additions": 1,
        "deletions": 0
    }
    
    with patch("agents.review_agent.run_linter", return_value=""):
        result = agent._review_single_file(
            file_data=file_data,
            system_prompt="system prompt",
            context="context",
            request_id="req123",
            pr_number=1,
            review_type="full PR"
        )
        
    assert result["filename"] == "test.py"
    assert len(result["comments"]) == 1
    assert result["comments"][0]["file"] == "test.py"
    assert "Test comment" in result["comments"][0]["comment"]
    assert "**[STYLE]**" in result["comments"][0]["comment"]

def test_review_single_file_parse_error(mock_dependencies):
    router = mock_dependencies["router"]
    
    mock_response = MagicMock()
    mock_response.success = True
    mock_response.content = 'This is not json'
    mock_response.provider = "openai"
    mock_response.model = "gpt-4o"
    mock_response.tokens_input = 100
    mock_response.tokens_output = 50
    mock_response.latency = 1.0
    router.generate.return_value = mock_response
    
    agent = ReviewAgent(repo_name="test/repo")
    file_data = {"filename": "test.py", "patch": "+print()", "status": "added", "additions": 1, "deletions": 0}
    
    with patch("agents.review_agent.run_linter", return_value=""):
        result = agent._review_single_file(file_data, "prompt", "", "req123", 1)
        
    assert result["filename"] == "test.py"
    assert len(result["comments"]) == 0
    assert any("Could not parse JSON" in log for log in result["logs"])

def test_post_comments(mock_dependencies):
    gh = mock_dependencies["gh_client"]
    gh.get_latest_commit_sha.return_value = "sha123"
    gh.comment_already_exists.return_value = False
    gh.get_valid_diff_lines.return_value = [10]
    gh.post_inline_comment.return_value = True
    
    agent = ReviewAgent(repo_name="test/repo")
    
    comments = [
        {"file": "test.py", "line": 10, "severity": "error", "comment": "Fix this"}
    ]
    
    mock_last_response = MagicMock()
    mock_last_response.tokens_input = 100
    mock_last_response.tokens_output = 50
    mock_last_response.provider = "openai"
    mock_last_response.model = "gpt-4o"
    
    posted = agent._post_comments(
        pr_number=1,
        all_parsed_comments=comments,
        reviewable_files=[{"filename": "test.py"}],
        last_response=mock_last_response,
        is_incremental=False,
        dedup=True
    )
    
    assert len(posted) == 1
    gh.post_inline_comment.assert_called_once_with(1, "sha123", "test.py", 10, "**[ERROR]** Fix this")
    gh.post_general_comment.assert_called_once()
