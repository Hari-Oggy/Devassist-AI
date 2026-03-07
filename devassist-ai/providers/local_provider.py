import time
from openai import OpenAI
from providers.base_provider import BaseProvider
from llm.schemas import LLMRequest, LLMResponse
from core.config import get_settings


class LocalProvider(BaseProvider):
    """
    Provider adapter for local LLMs using OpenAI-compatible APIs.
    Supports: Ollama, vLLM, LM Studio, or any OpenAI-compatible endpoint.
    """

    def __init__(self):
        settings = get_settings()
        self.client = OpenAI(
            base_url=settings.LOCAL_API_BASE,
            api_key=settings.LOCAL_API_KEY,
        )
        self.default_model = settings.LOCAL_MODEL

    def generate(self, request: LLMRequest) -> LLMResponse:
        settings = get_settings()
        model = request.metadata.get("model") or self.default_model
        temperature = request.temperature if request.temperature is not None else settings.LLM_TEMPERATURE
        max_tokens = request.max_tokens or settings.LLM_MAX_TOKENS

        start = time.time()
        try:
            completion = self.client.chat.completions.create(
                model=model,
                messages=request.messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            latency = time.time() - start

            choice = completion.choices[0]
            content = choice.message.content or ""
            usage = completion.usage

            return LLMResponse(
                content=content,
                model=model,
                provider="local",
                tokens_input=usage.prompt_tokens if usage else 0,
                tokens_output=usage.completion_tokens if usage else 0,
                latency=latency,
            )
        except Exception as e:
            return LLMResponse(
                model=model,
                provider="local",
                latency=time.time() - start,
                error=str(e),
            )
