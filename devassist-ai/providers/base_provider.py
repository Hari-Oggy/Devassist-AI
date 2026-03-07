"""
Abstract base class for all LLM provider adapters.
Every provider MUST implement generate(). stream() and tool_call() are optional.
"""

from abc import ABC, abstractmethod
from llm.schemas import LLMRequest, LLMResponse


class BaseProvider(ABC):
    """Interface contract that all provider adapters must follow."""

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Send a chat completion request and return a standardized response."""
        ...

    def stream(self, request: LLMRequest):
        """Stream a response. Default raises NotImplementedError."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support streaming.")

    def tool_call(self, request: LLMRequest) -> LLMResponse:
        """Execute a tool/function call. Default falls back to generate()."""
        return self.generate(request)
