import time
from openai import OpenAI
from providers.base_provider import BaseProvider
from llm.schemas import LLMRequest, LLMResponse
from core.config import get_settings


class OpenAIProvider(BaseProvider):
    """Provider adapter for the OpenAI API."""

    def __init__(self):
        settings = get_settings()
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def generate(self, request: LLMRequest) -> LLMResponse:
        settings = get_settings()
        model = request.metadata.get("model") or settings.LLM_MODEL
        temperature = request.temperature if request.temperature is not None else settings.LLM_TEMPERATURE
        max_tokens = request.max_tokens or settings.LLM_MAX_TOKENS

        start = time.time()
        try:
            kwargs = {
                "model": model,
                "messages": request.messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if request.tools:
                kwargs["tools"] = request.tools
                kwargs["tool_choice"] = "auto"

            completion = self.client.chat.completions.create(**kwargs)
            latency = time.time() - start

            choice = completion.choices[0]
            content = choice.message.content or ""
            usage = completion.usage

            return LLMResponse(
                content=content,
                model=completion.model,
                provider="openai",
                tokens_input=usage.prompt_tokens if usage else 0,
                tokens_output=usage.completion_tokens if usage else 0,
                latency=latency,
            )
        except Exception as e:
            return LLMResponse(
                model=model,
                provider="openai",
                latency=time.time() - start,
                error=str(e),
            )

    def tool_call(self, request: LLMRequest) -> LLMResponse:
        return self.generate(request)
