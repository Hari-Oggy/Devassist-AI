import time
from providers.base_provider import BaseProvider
from llm.schemas import LLMRequest, LLMResponse
from core.config import get_settings

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


class GeminiProvider(BaseProvider):
    """Provider adapter for Google Gemini API using the new google-genai SDK."""

    def __init__(self):
        if not HAS_GENAI:
            raise ImportError("google-genai package not installed. Run: pip install google-genai")
        settings = get_settings()
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

    def generate(self, request: LLMRequest) -> LLMResponse:
        settings = get_settings()
        model_name = request.metadata.get("model") or settings.LLM_MODEL
        temperature = request.temperature if request.temperature is not None else settings.LLM_TEMPERATURE
        max_tokens = request.max_tokens or settings.LLM_MAX_TOKENS

        # Build contents from messages
        system_instruction = None
        contents = []
        for msg in request.messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            elif msg["role"] == "user":
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=msg["content"])]))
            elif msg["role"] == "assistant":
                contents.append(types.Content(role="model", parts=[types.Part.from_text(text=msg["content"])]))

        start = time.time()
        try:
            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
            if system_instruction:
                config.system_instruction = system_instruction

            response = self.client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            latency = time.time() - start

            content = response.text if response.text else ""

            # Token usage
            tokens_in = 0
            tokens_out = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                tokens_in = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                tokens_out = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

            return LLMResponse(
                content=content,
                model=model_name,
                provider="gemini",
                tokens_input=tokens_in,
                tokens_output=tokens_out,
                latency=latency,
            )
        except Exception as e:
            return LLMResponse(
                model=model_name,
                provider="gemini",
                latency=time.time() - start,
                error=str(e),
            )
