"""
LLM Router — the central orchestrator for all LLM calls.

Responsibilities:
  1. Select best model for a task type using FALLBACK_CHAINS.
  2. Filter incompatible models via MODEL_REGISTRY capabilities.
  3. Retry with exponential backoff.
  4. Fallback to next model in the chain on failure.
  5. Optionally cache responses in Redis.
  6. Record structured metrics for every call.
"""

import hashlib
import json
import time
from typing import Optional

from core.config import get_settings
from core.logger import get_logger, generate_request_id
from llm.schemas import LLMRequest, LLMResponse
from llm.registry import MODEL_REGISTRY, get_fallback_chain, get_model_info
from llm.metrics import record_metrics
from providers.base_provider import BaseProvider

logger = get_logger("llm.router")


def _get_provider(provider_name: str) -> BaseProvider:
    """Factory: instantiate the correct provider adapter."""
    if provider_name == "openai":
        from providers.openai_provider import OpenAIProvider
        return OpenAIProvider()
    elif provider_name == "anthropic":
        from providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    elif provider_name == "gemini":
        from providers.gemini_provider import GeminiProvider
        return GeminiProvider()
    elif provider_name == "local":
        from providers.local_provider import LocalProvider
        return LocalProvider()
    else:
        raise ValueError(f"Unknown provider: {provider_name}")


def _make_cache_key(request: LLMRequest) -> str:
    """Generate a deterministic cache key from messages + metadata."""
    payload = json.dumps(request.messages, sort_keys=True) + request.task_type
    return "llm_cache:" + hashlib.sha256(payload.encode()).hexdigest()


_redis_client = None
_redis_checked = False


def _get_redis():
    """Lazy Redis client for caching. Cached after first attempt."""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    try:
        import redis
        settings = get_settings()
        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=1)
        r.ping()
        _redis_client = r
    except Exception:
        _redis_client = None
    return _redis_client


class LLMRouter:
    """
    Central LLM router. Agents call router.generate(request) and never
    interact with providers directly.
    """

    def __init__(self):
        self.settings = get_settings()

    def _provider_is_available(self, provider_name: str) -> bool:
        """Check if a provider has the required API key configured."""
        s = self.settings
        placeholder_values = {"your_openai_api_key_here", "your_anthropic_api_key_here", "your_gemini_api_key_here"}

        if provider_name == "openai":
            return bool(s.OPENAI_API_KEY) and s.OPENAI_API_KEY not in placeholder_values
        elif provider_name == "anthropic":
            return bool(s.ANTHROPIC_API_KEY) and s.ANTHROPIC_API_KEY not in placeholder_values
        elif provider_name == "gemini":
            return bool(s.GEMINI_API_KEY) and s.GEMINI_API_KEY not in placeholder_values
        elif provider_name == "local":
            return True  # Local LLMs don't need an API key
        return False

    def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Main entry point. Routes the request through:
        cache check → model selection → provider call → fallback → metrics.
        """
        request_id = request.metadata.get("request_id") or generate_request_id()
        request.metadata["request_id"] = request_id

        # 1. Check cache
        if self.settings.CACHE_ENABLED:
            cached = self._check_cache(request)
            if cached:
                logger.info("Cache hit", extra={"request_id": request_id, "task_type": request.task_type})
                return cached

        # 2. Determine model chain
        chain = self._build_chain(request)
        if not chain:
            return LLMResponse(error="No compatible models found for this task. Check your API keys in .env", provider="router")

        logger.info(f"Model chain: {chain}", extra={"request_id": request_id})

        # 3. Try each model in the chain with retries
        fallback_used = False
        for idx, model_name in enumerate(chain):
            model_info = get_model_info(model_name)
            if not model_info:
                continue

            provider_name = model_info["provider"]
            if idx > 0:
                fallback_used = True

            try:
                provider = _get_provider(provider_name)
            except Exception as e:
                logger.warning(f"Cannot instantiate provider {provider_name}: {e}",
                               extra={"request_id": request_id})
                continue

            # Inject the selected model into metadata for the provider
            request.metadata["model"] = model_name

            response = self._call_with_retries(provider, request, request_id)

            if response.success:
                response.fallback_used = fallback_used
                record_metrics(response, task_type=request.task_type, request_id=request_id)

                # Store in cache
                if self.settings.CACHE_ENABLED:
                    self._store_cache(request, response)

                return response
            else:
                logger.warning(
                    f"Model {model_name} failed: {response.error}. Trying next in chain...",
                    extra={"request_id": request_id, "model": model_name, "provider": provider_name}
                )

        # All models exhausted
        final_error = LLMResponse(
            error="All models in the fallback chain failed.",
            provider="router",
            fallback_used=True,
        )
        record_metrics(final_error, task_type=request.task_type, request_id=request_id)
        return final_error

    def _build_chain(self, request: LLMRequest) -> list[str]:
        """
        Build the ordered list of models to try.
        1. Put the user's configured model first.
        2. Filter out any models whose provider has no API key.
        3. Filter out models that don't support required features (e.g., tools).
        """
        chain = get_fallback_chain(request.task_type)

        # Front-load the configured model
        configured_model = self.settings.LLM_MODEL
        if configured_model and configured_model not in chain:
            chain = [configured_model] + chain
        elif configured_model and configured_model in chain:
            chain.remove(configured_model)
            chain = [configured_model] + chain

        # Remove models whose providers have no API key configured
        chain = [
            m for m in chain
            if m in MODEL_REGISTRY and self._provider_is_available(MODEL_REGISTRY[m]["provider"])
        ]

        # Filter models that require tools but model doesn't support them
        if request.tools:
            chain = [m for m in chain if MODEL_REGISTRY.get(m, {}).get("supports_tools", False)]

        return chain

    def _call_with_retries(self, provider: BaseProvider, request: LLMRequest, request_id: str) -> LLMResponse:
        """Call the provider with exponential backoff retries."""
        max_retries = self.settings.LLM_MAX_RETRIES
        for attempt in range(max_retries):
            response = provider.generate(request)
            if response.success:
                return response

            if attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.info(
                    f"Retry {attempt + 1}/{max_retries} in {wait}s",
                    extra={"request_id": request_id, "error": response.error}
                )
                time.sleep(wait)

        return response  # Last failed response

    def _check_cache(self, request: LLMRequest) -> Optional[LLMResponse]:
        """Check Redis cache for a previous identical request."""
        client = _get_redis()
        if not client:
            return None
        try:
            key = _make_cache_key(request)
            data = client.get(key)
            if data:
                resp = LLMResponse(**json.loads(data))
                resp.cached = True
                return resp
        except Exception:
            pass
        return None

    def _store_cache(self, request: LLMRequest, response: LLMResponse) -> None:
        """Store a successful response in Redis cache."""
        client = _get_redis()
        if not client:
            return
        try:
            key = _make_cache_key(request)
            client.setex(key, self.settings.CACHE_TTL, response.model_dump_json())
        except Exception:
            pass
