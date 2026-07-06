from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


class LLMRequest(BaseModel):
    """Standardized request object for all LLM calls. Agents build these; the Router dispatches them."""

    task_type: str = Field(description="Task type for routing: 'code_review', 'documentation', 'general'")
    messages: list[dict[str, str]] = Field(description="Chat messages in [{role, content}] format")
    temperature: Optional[float] = Field(default=None, description="Override temperature (uses config default if None)")
    max_tokens: Optional[int] = Field(default=None, description="Override max tokens")
    tools: Optional[list[dict]] = Field(default=None, description="Tool definitions for function/tool calling")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata (request_id, file, pr_number, etc.)")


class LLMResponse(BaseModel):
    """Standardized response object returned by all providers through the Router."""

    content: str = Field(default="", description="The generated text content")
    tool_calls: Optional[list[dict]] = Field(default=None, description="Structured tool/function calls returned by the model")
    model: str = Field(default="", description="Model that was actually used")
    provider: str = Field(default="", description="Provider that served the request")
    tokens_input: int = Field(default=0, description="Input/prompt token count")
    tokens_output: int = Field(default=0, description="Output/completion token count")
    latency: float = Field(default=0.0, description="Request-to-response time in seconds")
    error: Optional[str] = Field(default=None, description="Error message if the request failed")
    fallback_used: bool = Field(default=False, description="True if a fallback model was used")
    cached: bool = Field(default=False, description="True if result was served from cache")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def success(self) -> bool:
        return self.error is None
