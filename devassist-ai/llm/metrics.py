"""
Metrics tracking for every LLM request.
Logs structured JSON to the observability system.
"""

from core.logger import get_logger
from llm.schemas import LLMResponse

logger = get_logger("llm.metrics")

# Rough cost estimates per 1K tokens (USD) — update as pricing changes
COST_PER_1K_TOKENS: dict[str, dict[str, float]] = {
    "gpt-4o":                       {"input": 0.005,  "output": 0.015},
    "gpt-4o-mini":                  {"input": 0.00015, "output": 0.0006},
    "gpt-3.5-turbo":                {"input": 0.0005, "output": 0.0015},
    "claude-3-5-sonnet-20241022":   {"input": 0.003,  "output": 0.015},
    "claude-3-haiku-20240307":      {"input": 0.00025, "output": 0.00125},
    "gemini-1.5-pro":               {"input": 0.00125, "output": 0.005},
    "gemini-1.5-flash":             {"input": 0.000075, "output": 0.0003},
}


def estimate_cost(model: str, tokens_input: int, tokens_output: int) -> float:
    """Estimate the cost of a request based on token counts."""
    rates = COST_PER_1K_TOKENS.get(model)
    if not rates:
        return 0.0
    return (tokens_input / 1000 * rates["input"]) + (tokens_output / 1000 * rates["output"])


def record_metrics(response: LLMResponse, task_type: str = "", request_id: str = "") -> None:
    """Log a structured metrics entry for an LLM response."""
    cost = estimate_cost(response.model, response.tokens_input, response.tokens_output)

    logger.info(
        "LLM request completed",
        extra={
            "request_id": request_id,
            "task_type": task_type,
            "model": response.model,
            "provider": response.provider,
            "latency": round(response.latency, 3),
            "tokens_input": response.tokens_input,
            "tokens_output": response.tokens_output,
            "fallback_used": response.fallback_used,
            "estimated_cost_usd": round(cost, 6),
            "error": response.error,
        },
    )
