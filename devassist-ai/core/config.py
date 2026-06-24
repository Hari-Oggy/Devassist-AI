import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Central configuration loaded from .env file. All components import from here."""

    # --- LLM Provider Configuration ---
    LLM_PROVIDER: str = Field(default="openai", description="Primary LLM provider: openai, anthropic, gemini, local")
    LLM_MODEL: str = Field(default="gemini-2.0-flash", description="Default model name for the selected provider")
    LLM_TEMPERATURE: float = Field(default=0.0, description="Default temperature for LLM calls")
    LLM_MAX_TOKENS: int = Field(default=4096, description="Default max tokens for LLM responses")

    BASE_URL:str = Field(default="https://api.openai.com/v1",description="Base url nvidia free model endpoints")
    # Task-specific temperature overrides
    REVIEW_TEMPERATURE: float = Field(default=0.0, description="Temperature for code review tasks")
    DOC_TEMPERATURE: float = Field(default=0.2, description="Temperature for documentation tasks")

    # --- API Keys ---
    NVIDIA_API_KEY:Optional[str]=Field(default=None,description="Nvidia API Key")
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API Key")
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, description="Anthropic API Key")
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="Google Gemini API Key")

    # --- Local LLM Configuration ---
    LOCAL_API_BASE: str = Field(default="http://localhost:11434/v1", description="Base URL for local LLM (Ollama/vLLM/LM Studio)")
    LOCAL_API_KEY: str = Field(default="not-needed", description="API key for local LLM (often not required)")
    LOCAL_MODEL: str = Field(default="llama3.2", description="Model name for local LLM")

    # --- GitHub Configuration ---
    GITHUB_TOKEN: Optional[str] = Field(default=None, description="GitHub Personal Access Token")
    GITHUB_REPO: Optional[str] = Field(default=None, description="GitHub repo in owner/repo format")

    # --- GitHub App (Bot Identity) ---
    GITHUB_APP_ID: Optional[int] = Field(default=None, description="GitHub App ID for bot identity")
    GITHUB_APP_PRIVATE_KEY_PATH: Optional[str] = Field(default=None, description="Path to .pem private key file for GitHub App")
    GITHUB_APP_INSTALLATION_ID: Optional[int] = Field(default=None, description="GitHub App installation ID for the target repo")

    # --- RAG Configuration ---
    CODEBASE_PATH: str = Field(default="./local_repo", description="Path to the codebase to index")
    FAISS_INDEX_PATH: str = Field(default="./data/faiss_index", description="Path to FAISS index storage")

    # --- Infrastructure ---
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis broker URL for Celery")
    API_HOST: str = Field(default="0.0.0.0", description="API server host")
    API_PORT: int = Field(default=8000, description="API server port")

    # --- Retry / Resilience ---
    LLM_MAX_RETRIES: int = Field(default=3, description="Max retries for LLM API calls")
    REVIEW_TIMEOUT: int = Field(default=300, description="Timeout in seconds for review tasks (per-file reviews need more time)")
    DOC_TIMEOUT: int = Field(default=120, description="Timeout in seconds for documentation tasks")

    # --- Cache ---
    CACHE_ENABLED: bool = Field(default=False, description="Enable Redis-based LLM response caching")
    CACHE_TTL: int = Field(default=3600, description="Cache TTL in seconds")

    # --- Webhook / Polling ---
    WEBHOOK_SECRET: str = Field(default="", description="GitHub webhook HMAC secret for signature verification")
    BOT_NAME: str = Field(default="devassist-ai", description="Bot identity name used in comment markers")
    POLLING_ENABLED: bool = Field(default=False, description="Enable GitHub polling mode (alternative to webhooks)")
    POLLING_INTERVAL: int = Field(default=30, description="Seconds between GitHub polls")

    # --- Review Protection ---
    MAX_DIFF_SIZE: int = Field(default=15000, description="Max diff characters to send to LLM (truncate beyond)")
    REVIEW_DEBOUNCE_SECONDS: int = Field(default=60, description="Min seconds between reviews of the same PR")
    SKIP_DRAFT_PRS: bool = Field(default=True, description="Skip draft PRs in webhook/poller")
    REQUIRE_LABEL: str = Field(default="", description="If set, only review PRs with this label")

    # --- CORS / API Security ---
    CORS_ORIGINS: str = Field(default="http://localhost:8501", description="Comma-separated allowed CORS origins")
    API_KEY: str = Field(default="", description="API key to protect FastAPI endpoints (leave empty to disable)")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Returns a singleton Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
