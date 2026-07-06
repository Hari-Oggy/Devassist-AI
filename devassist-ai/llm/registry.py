"""
Model capability registry. Used by the Router to filter compatible models
and build intelligent fallback chains.
"""

MODEL_REGISTRY: dict[str, dict] = {


      # --- NVIDIA ---
    "meta/llama-3.1-70b-instruct": {
        "provider": "nvidia",
        "context_window": 128000,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": False,
    },
    "meta/llama-3.1-8b-instruct": {
        "provider": "nvidia",
        "context_window": 128000,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": False,
    },
    "deepseek-ai/deepseek-v4-pro": {
        "provider": "nvidia",
        "context_window": 128000,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": False,
    },
    "z-ai/glm-5.1": {
        "provider": "nvidia",
        "context_window": 128000,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": False,
    },
    "z-ai/glm-5.2": {
        "provider": "nvidia",
        "context_window": 128000,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": False,
    },
    "minimaxai/minimax-m3": {
        "provider": "nvidia",
        "context_window": 40960,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": False,
    },

    # --- OpenRouter ---
    "moonshotai/moonshot-v1-8k": {
        "provider": "openrouter",
        "context_window": 8192,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": False,
    },
    "deepseek/deepseek-chat:free": {
        "provider": "openrouter",
        "context_window": 32768,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": False,
    },

    # --- Local LLM (defaults, user can override model name) ---
    "qwen2.5-7b-instruct": {
        "provider": "local",
        "context_window": 32768,
        "supports_tools": False,
        "supports_json": True,
        "supports_vision": False,
    },
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

    # # --- Anthropic ---
    # "claude-3-5-sonnet-20241022": {
    #     "provider": "anthropic",
    #     "context_window": 200000,
    #     "supports_tools": True,
    #     "supports_json": True,
    #     "supports_vision": True,
    # },
    # "claude-3-haiku-20240307": {
    #     "provider": "anthropic",
    #     "context_window": 200000,
    #     "supports_tools": True,
    #     "supports_json": True,
    #     "supports_vision": True,
    # },

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

  
}


# --- Fallback Chains (task_type -> ordered list of models to try) ---
FALLBACK_CHAINS: dict[str, list[str]] = {
    "code_review": [
        "meta/llama-3.1-70b-instruct",
        "openai/gpt-oss-120b",
        "gpt-4o",
        "claude-3-5-sonnet-20241022",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "llama3",
    ],
    "documentation": [
        "meta/llama-3.1-70b-instruct",
        "openai/gpt-oss-120b",
        "claude-3-5-sonnet-20241022",
        "gpt-4o",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "llama3",
    ],
    "general": [
        "meta/llama-3.1-8b-instruct",
        "qwen2.5-7b-instruct",
        "gpt-4o-mini",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "llama3",
    ],
    "context_distillation": [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gpt-4o-mini",
        "claude-3-haiku-20240307",
        "meta/llama-3.1-8b-instruct",
        "qwen2.5-7b-instruct",
    ],
    "finding_validation": [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gpt-4o-mini",
        "claude-3-haiku-20240307",
        "meta/llama-3.1-8b-instruct",
        "qwen2.5-7b-instruct",
    ],
}


def get_model_info(model_name: str) -> dict | None:
    """Returns capability info for a model, or None if not found."""
    from core.config import get_settings
    from core.pipeline_config import get_pipeline_settings
    
    settings = get_settings()
    pipe_settings = get_pipeline_settings()
    
    configured_models = []
    if settings.LLM_MODEL:
        configured_models.append(settings.LLM_MODEL)
    if pipe_settings.DISTILL_MODEL:
        configured_models.append(pipe_settings.DISTILL_MODEL)
    if pipe_settings.REASON_MODEL:
        configured_models.append(pipe_settings.REASON_MODEL)
    if pipe_settings.VALIDATE_MODEL:
        configured_models.append(pipe_settings.VALIDATE_MODEL)

    info = None
    if model_name in MODEL_REGISTRY:
        info = dict(MODEL_REGISTRY[model_name])
    
    if model_name in configured_models:
        provider = settings.LLM_PROVIDER
        
        # If we have base info, override its provider with the user's explicit choice
        if info:
            info["provider"] = provider
            return info
            
        lower_name = model_name.lower()
        valid_providers = ["nvidia","openrouter", "local","openai", "gemini",  "anthropic" ]
        
        # Check if the prefix contains a valid provider
        import re
        tokens = re.split(r'[/:\-_]', lower_name)
        if tokens:
            prefix = tokens[0]
            for vp in valid_providers:
                if vp == prefix or vp in prefix or prefix.startswith(vp):
                    provider = vp
                    break
            # Additional fallback mappings for common provider names
            if provider == settings.LLM_PROVIDER:
                if "claude" in prefix:
                    provider = "anthropic"
                elif "gpt" in prefix:
                    provider = "openai"
                    
        return {
            "provider": provider,
            "context_window": 128000,
            "supports_tools": True,
            "supports_json": True,
            "supports_vision": False,
        }
        
    return info


def get_fallback_chain(task_type: str) -> list[str]:
    """Returns the fallback model chain for a given task type."""
    return FALLBACK_CHAINS.get(task_type, FALLBACK_CHAINS["general"])
