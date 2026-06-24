"""Pydantic models for the multi-stage ensemble review pipeline.

These schemas define the data contracts between pipeline stages
(distill → reason → validate) and the final aggregated result.
"""

from pydantic import BaseModel, Field
from typing import Optional


class DistillationResult(BaseModel):
    """Output of the distillation stage — a condensed summary of the diff
    that guides the reasoning stage's focus areas."""

    change_type: str = Field(
        description=(
            "Primary category of the change: "
            "'refactor' | 'feature' | 'bugfix' | 'config' | 'test' | 'mixed'"
        ),
    )
    risk_areas: list[str] = Field(
        description=(
            "Domains that may be affected, "
            "e.g. ['security', 'concurrency', 'api_contract']"
        ),
    )
    summary: str = Field(
        description="Condensed, human-readable description of the changes",
    )
    key_concerns: list[str] = Field(
        description="Specific questions or focus points for the reasoning stage",
    )
    estimated_complexity: str = Field(
        description="Rough complexity bucket: 'low' | 'medium' | 'high'",
    )
    tokens_used: int = Field(
        default=0,
        description="Total tokens consumed during distillation",
    )
    latency_seconds: float = Field(
        default=0.0,
        description="Wall-clock time for the distillation call in seconds",
    )
    model_used: str = Field(
        default="",
        description="Model identifier used for distillation",
    )

    model_config = {"protected_namespaces": ()}


class ValidatedFinding(BaseModel):
    """A single review finding that has been validated by the pipeline."""

    file: str = Field(
        description="Relative path to the file containing the finding",
    )
    line: int = Field(
        description="1-based line number where the finding applies",
    )
    severity: str = Field(
        description="Impact level: 'error' | 'warning' | 'suggestion'",
    )
    category: str = Field(
        description=(
            "Finding domain: 'security' | 'correctness' | 'reliability' | "
            "'performance' | 'maintainability' | 'style'"
        ),
    )
    comment: str = Field(
        description="Human-readable explanation of the issue",
    )
    code_fix: Optional[str] = Field(
        default=None,
        description="Optional suggested code replacement",
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence score from 0.0 (speculative) to 1.0 (certain)",
    )
    tool_source: str = Field(
        default="ensemble_reason",
        description=(
            "Origin of the finding: "
            "'ensemble_reason' | 'linter' | 'codegraph'"
        ),
    )
    validation_notes: Optional[str] = Field(
        default=None,
        description="Notes added by the validation stage about this finding",
    )


class StageResult(BaseModel):
    """Telemetry and output captured from a single pipeline stage execution."""

    stage_name: str = Field(
        description="Identifier for the stage, e.g. 'distill', 'reason', 'validate'",
    )
    model: str = Field(
        description="Model identifier used in this stage",
    )
    provider: str = Field(
        description="Provider that served the request for this stage",
    )
    tokens_input: int = Field(
        default=0,
        description="Input/prompt token count for this stage",
    )
    tokens_output: int = Field(
        default=0,
        description="Output/completion token count for this stage",
    )
    latency_seconds: float = Field(
        default=0.0,
        description="Wall-clock time for this stage in seconds",
    )
    cost_estimate: float = Field(
        default=0.0,
        description="Estimated cost in USD for this stage",
    )
    success: bool = Field(
        default=True,
        description="Whether the stage completed without errors",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if the stage failed",
    )
    raw_output: str = Field(
        default="",
        description="The raw LLM output text for this stage",
    )


class PipelineResult(BaseModel):
    """Aggregated result of the full review pipeline (fast or ensemble mode)."""

    findings: list[ValidatedFinding] = Field(
        default_factory=list,
        description="All validated review findings produced by the pipeline",
    )
    mode: str = Field(
        default="fast",
        description="Pipeline execution mode: 'fast' | 'ensemble'",
    )
    stages_completed: list[str] = Field(
        default_factory=list,
        description="Ordered list of stages that ran, e.g. ['distill', 'reason', 'validate']",
    )
    distillation: Optional[DistillationResult] = Field(
        default=None,
        description="Distillation output (present only in ensemble mode)",
    )
    total_tokens_input: int = Field(
        default=0,
        description="Sum of input tokens across all stages",
    )
    total_tokens_output: int = Field(
        default=0,
        description="Sum of output tokens across all stages",
    )
    total_cost_estimate: float = Field(
        default=0.0,
        description="Estimated total cost in USD across all stages",
    )
    duration_seconds: float = Field(
        default=0.0,
        description="Total wall-clock duration of the pipeline run in seconds",
    )
    model_used: str = Field(
        default="",
        description="Last model used (retained for backward compatibility)",
    )
    provider_used: str = Field(
        default="",
        description="Last provider used (retained for backward compatibility)",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Non-fatal errors encountered during the pipeline run",
    )

    model_config = {"protected_namespaces": ()}

    @property
    def success(self) -> bool:
        """Pipeline is considered successful when no errors occurred
        or when at least some findings were produced despite errors."""
        return len(self.errors) == 0 or len(self.findings) > 0
