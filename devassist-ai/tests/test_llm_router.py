import pytest
from unittest.mock import patch, MagicMock
from llm.router import LLMRouter
from llm.schemas import LLMRequest, LLMResponse

@pytest.fixture
def mock_settings():
    with patch("llm.router.get_settings") as mock:
        settings_mock = MagicMock()
        settings_mock.CACHE_ENABLED = False
        settings_mock.LLM_PROVIDER = "openai"
        settings_mock.LLM_MODEL = "gpt-4o"
        settings_mock.OPENAI_API_KEY = "sk-test-key"
        settings_mock.ANTHROPIC_API_KEY = ""
        settings_mock.GEMINI_API_KEY = ""
        settings_mock.LLM_MAX_RETRIES = 1
        mock.return_value = settings_mock
        yield settings_mock

def test_router_initialization(mock_settings):
    router = LLMRouter()
    assert router.settings.LLM_PROVIDER == "openai"
    assert router.settings.LLM_MODEL == "gpt-4o"

@patch("llm.router.get_fallback_chain")
@patch("llm.router.get_model_info")
def test_build_chain(mock_model_info, mock_fallback_chain, mock_settings):
    mock_fallback_chain.return_value = ["gpt-4o", "claude-3.5-sonnet", "gemini-2.0-flash"]
    mock_model_info.side_effect = lambda m: {
        "gpt-4o": {"provider": "openai", "supports_tools": True},
        "claude-3.5-sonnet": {"provider": "anthropic", "supports_tools": True},
        "gemini-2.0-flash": {"provider": "gemini", "supports_tools": True},
    }.get(m)
    
    router = LLMRouter()
    req = LLMRequest(task_type="code_review", messages=[])
    
    chain = router._build_chain(req)
    
    # Since only OPENAI_API_KEY is set in mock_settings, others should be filtered out
    assert chain == ["gpt-4o"]

@patch("llm.router._get_provider")
@patch("llm.router.get_model_info")
def test_generate_success(mock_model_info, mock_get_provider, mock_settings):
    mock_model_info.return_value = {"provider": "openai", "supports_tools": True}
    
    mock_provider = MagicMock()
    mock_provider.generate.return_value = LLMResponse(
        content="success content",
        success=True,
        model="gpt-4o",
        provider="openai",
        tokens_input=10,
        tokens_output=20
    )
    mock_get_provider.return_value = mock_provider
    
    router = LLMRouter()
    
    with patch.object(router, "_build_chain", return_value=["gpt-4o"]):
        req = LLMRequest(task_type="code_review", messages=[])
        res = router.generate(req)
        
        assert res.success is True
        assert res.content == "success content"
        assert res.fallback_used is False

@patch("llm.router._get_provider")
@patch("llm.router.get_model_info")
def test_generate_fallback(mock_model_info, mock_get_provider, mock_settings):
    mock_model_info.return_value = {"provider": "openai", "supports_tools": True}
    
    # Provider fails on first call, succeeds on second (simulating fallback behavior if multiple models exist)
    # Wait, the fallback is across models. So if we have ["gpt-4o", "gpt-4o-mini"]
    mock_provider1 = MagicMock()
    mock_provider1.generate.return_value = LLMResponse(success=False, error="timeout", model="gpt-4o", provider="openai")
    
    mock_provider2 = MagicMock()
    mock_provider2.generate.return_value = LLMResponse(
        content="fallback success",
        success=True,
        model="gpt-4o-mini",
        provider="openai",
        tokens_input=10,
        tokens_output=20
    )
    
    mock_get_provider.side_effect = [mock_provider1, mock_provider2]
    
    router = LLMRouter()
    
    with patch.object(router, "_build_chain", return_value=["gpt-4o", "gpt-4o-mini"]):
        req = LLMRequest(task_type="code_review", messages=[])
        res = router.generate(req)
        
        assert res.success is True
        assert res.content == "fallback success"
        assert res.fallback_used is True
