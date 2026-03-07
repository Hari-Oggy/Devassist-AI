import time
from providers.base_provider import BaseProvider
from llm.schemas import LLMRequest, LLMResponse
from core.config import get_settings

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


class AnthropicProvider(BaseProvider):
    """Provider adapter for the Anthropic (Claude) API."""

    def __init__(self):
        if not HAS_ANTHROPIC:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def generate(self, request: LLMRequest) -> LLMResponse:
        settings = get_settings()
        model = request.metadata.get("model") or settings.LLM_MODEL
        temperature = request.temperature if request.temperature is not None else settings.LLM_TEMPERATURE
        max_tokens = request.max_tokens or settings.LLM_MAX_TOKENS

        # Anthropic API separates system messages from user messages
        system_msg = ""
        messages = []
        for msg in request.messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                messages.append({"role": msg["role"], "content": msg["content"]})

        start = time.time()
        try:
            kwargs = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
                "temperature": temperature,
            }
            if system_msg:
                kwargs["system"] = system_msg
            if request.tools:
                kwargs["tools"] = request.tools

            response = self.client.messages.create(**kwargs)
            latency = time.time() - start

            content = ""
            for block in response.content:
                if hasattr(block, "text"):
                    content += block.text

            return LLMResponse(
                content=content,
                model=response.model,
                provider="anthropic",
                tokens_input=response.usage.input_tokens,
                tokens_output=response.usage.output_tokens,
                latency=latency,
            )
        except Exception as e:
            return LLMResponse(
                model=model,
                provider="anthropic",
                latency=time.time() - start,
                error=str(e),
            )
