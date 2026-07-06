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

    def generate(self, request: LLMRequest, tool_executor=None) -> LLMResponse:
        settings = get_settings()
        model = request.metadata.get("model") or settings.LLM_MODEL
        temperature = request.temperature if request.temperature is not None else settings.LLM_TEMPERATURE
        max_tokens = request.max_tokens or settings.LLM_MAX_TOKENS

        messages = list(request.messages)
        total_input_tokens = 0
        total_output_tokens = 0

        while True:
            start = time.time()
            try:
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                # Only enforce JSON object if not calling tools
                if request.task_type == "code_review" and not request.tools:
                    kwargs["response_format"] = {"type": "json_object"}
                if request.tools:
                    kwargs["tools"] = [
                        {
                            "type": "function",
                            "function": {
                                "name": t["name"],
                                "description": t.get("description", ""),
                                "parameters": t.get("input_schema", {})
                            }
                        } for t in request.tools
                    ]
                    kwargs["tool_choice"] = "auto"

                completion = self.client.chat.completions.create(**kwargs)
                latency = time.time() - start

                choice = completion.choices[0]
                content = choice.message.content or ""
                usage = completion.usage
                
                if usage:
                    total_input_tokens += usage.prompt_tokens
                    total_output_tokens += usage.completion_tokens

                # If the model requested tool execution and we have an executor
                if hasattr(choice.message, "tool_calls") and choice.message.tool_calls and tool_executor:
                    # Append assistant message with tool calls in-place for loop
                    assistant_msg = {
                        "role": "assistant",
                        "content": content,
                    }
                    # Convert OpenAI tool calls to serializable dicts
                    tcs = []
                    for tc in choice.message.tool_calls:
                        tcs.append({
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        })
                    assistant_msg["tool_calls"] = tcs
                    messages.append(assistant_msg)

                    for tc in choice.message.tool_calls:
                        tool_name = tc.function.name
                        try:
                            tool_args = json.loads(tc.function.arguments)
                        except Exception:
                            tool_args = {}
                        
                        # Call synchronous tool executor
                        tool_res = tool_executor(tool_name, tool_args)
                        
                        # Convert tool output (MCP format) to plain text
                        content_list = tool_res.get("content", [])
                        text_parts = [item.get("text", "") for item in content_list if item.get("type") == "text"]
                        tool_result_str = "\n".join(text_parts) if text_parts else json.dumps(tool_res)

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tool_name,
                            "content": tool_result_str
                        })
                    continue

                tool_calls = None
                if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
                    tool_calls = [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in choice.message.tool_calls
                    ]

                return LLMResponse(
                    content=content,
                    tool_calls=tool_calls,
                    model=completion.model,
                    provider="openai",
                    tokens_input=total_input_tokens,
                    tokens_output=total_output_tokens,
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
