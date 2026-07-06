import time
import json
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

    def generate(self, request: LLMRequest, tool_executor=None) -> LLMResponse:
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

        total_input_tokens = 0
        total_output_tokens = 0

        while True:
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
                    kwargs["tools"] = [
                        {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "input_schema": t.get("input_schema", {})
                        } for t in request.tools
                    ]

                response = self.client.messages.create(**kwargs)
                latency = time.time() - start

                total_input_tokens += response.usage.input_tokens
                total_output_tokens += response.usage.output_tokens

                content = ""
                tool_use_blocks = []
                for block in response.content:
                    if block.type == "text":
                        content += block.text
                    elif block.type == "tool_use":
                        tool_use_blocks.append(block)

                # Check if model requested tool use and we have an executor
                if tool_use_blocks and tool_executor:
                    # Append assistant message (raw blocks)
                    assistant_content = []
                    if content:
                        assistant_content.append({"type": "text", "text": content})
                    for block in tool_use_blocks:
                        assistant_content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input
                        })
                    messages.append({"role": "assistant", "content": assistant_content})

                    # Execute tools and build tool result blocks for next user turn
                    tool_result_content = []
                    for block in tool_use_blocks:
                        tool_name = block.name
                        tool_args = block.input
                        
                        tool_res = tool_executor(tool_name, tool_args)
                        
                        # Convert tool output (MCP format) to plain text
                        content_list = tool_res.get("content", [])
                        text_parts = [item.get("text", "") for item in content_list if item.get("type") == "text"]
                        tool_result_str = "\n".join(text_parts) if text_parts else json.dumps(tool_res)

                        tool_result_content.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": tool_result_str
                        })
                    messages.append({"role": "user", "content": tool_result_content})
                    continue

                tool_calls = None
                if tool_use_blocks:
                    tool_calls = []
                    for block in tool_use_blocks:
                        tool_calls.append({
                            "id": block.id,
                            "type": "function",
                            "function": {
                                "name": block.name,
                                "arguments": json.dumps(block.input)
                            }
                        })

                return LLMResponse(
                    content=content,
                    tool_calls=tool_calls,
                    model=response.model,
                    provider="anthropic",
                    tokens_input=total_input_tokens,
                    tokens_output=total_output_tokens,
                    latency=latency,
                )
            except Exception as e:
                return LLMResponse(
                    model=model,
                    provider="anthropic",
                    latency=time.time() - start,
                    error=str(e),
                )
