"""
Model capability registry. Used by the Router to filter compatible models
and build intelligent fallback chains.
"""

MODEL_REGISTRY: dict[str, dict] = {
    # --- OpenAI ---
    "gpt-4o": {
        "provider": "openai",
        "context_window": 128000,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "context_window": 128000,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
    },

    # --- Anthropic ---
    "claude-3-5-sonnet-20241022": {
        "provider": "anthropic",
        "context_window": 200000,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
    },
    "claude-3-haiku-20240307": {
        "provider": "anthropic",
        "context_window": 200000,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
    },

    # --- Gemini ---
    "gemini-2.5-pro": {
        "provider": "gemini",
        "context_window": 1048576,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
    },
    "gemini-2.5-flash": {
        "provider": "gemini",
        "context_window": 1048576,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
    },
    "gemini-2.0-flash": {
        "provider": "gemini",
        "context_window": 1048576,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
    },
    "gemini-3-flash-preview": {
        "provider": "gemini",
        "context_window": 1048576,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
    },

    # --- Local LLM (defaults, user can override model name) ---
    "llama3": {
        "provider": "local",
        "context_window": 8192,
        "supports_tools": False,
        "supports_json": False,
        "supports_vision": False,
    },
    "codellama": {
        "provider": "local",
        "context_window": 16384,
        "supports_tools": False,
        "supports_json": False,
        "supports_vision": False,
    },
    "mistral": {
        "provider": "local",
        "context_window": 32768,
        "supports_tools": False,
        "supports_json": False,
        "supports_vision": False,
    },
}


# --- Fallback Chains (task_type -> ordered list of models to try) ---
FALLBACK_CHAINS: dict[str, list[str]] = {
    "code_review": [
        "gpt-4o",
        "claude-3-5-sonnet-20241022",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "llama3",
    ],
    "documentation": [
        "claude-3-5-sonnet-20241022",
        "gpt-4o",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "llama3",
    ],
    "general": [
        "gpt-4o-mini",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "llama3",
    ],
}


def get_model_info(model_name: str) -> dict | None:
    """Returns capability info for a model, or None if not found."""
    return MODEL_REGISTRY.get(model_name)


def get_fallback_chain(task_type: str) -> list[str]:
    """Returns the fallback model chain for a given task type."""
    return FALLBACK_CHAINS.get(task_type, FALLBACK_CHAINS["general"])
