import time
from openai import OpenAI
from providers.base_provider import BaseProvider
from llm.schemas import LLMRequest, LLMResponse
from core.config import get_settings


class OpenRouterProvider(BaseProvider):
    """Provider adapter for the OpenRouter API."""

    def __init__(self):
        settings = get_settings()
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
        )

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
                "extra_headers": {
                    "HTTP-Referer": "https://github.com/devassist-ai",
                    "X-Title": "DevAssist AI",
                }
            }
            if request.task_type == "code_review":
                kwargs["response_format"] = {"type": "json_object"}
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
                provider="openrouter",
                tokens_input=usage.prompt_tokens if usage else 0,
                tokens_output=usage.completion_tokens if usage else 0,
                latency=latency,
            )
        except Exception as e:
            return LLMResponse(
                model=model,
                provider="openrouter",
                latency=time.time() - start,
                error=str(e),
            )

    def tool_call(self, request: LLMRequest) -> LLMResponse:
        return self.generate(request)
