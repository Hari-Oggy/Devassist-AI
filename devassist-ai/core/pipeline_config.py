from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class PipelineSettings(BaseSettings):
    """Pipeline-specific configuration for the distill-reason-validate review flow.

    Loaded from .env alongside the main Settings class. Controls review mode
    selection, per-stage model/temperature/token overrides, validation
    thresholds, and agentic-script limits.
    """

    # --- Review Mode ---
    REVIEW_MODE: str = Field(
        default="fast",
        description="Pipeline review mode: 'fast' (single-pass) or 'ensemble' (distill-reason-validate)",
    )

    # --- Distill Stage ---
    DISTILL_MODEL: str = Field(
        default="gemini-2.5-flash",
        description="Model used for the distillation stage",
    )
    DISTILL_TEMPERATURE: float = Field(
        default=0.1,
        description="Temperature for the distillation stage",
    )
    DISTILL_MAX_TOKENS: int = Field(
        default=2048,
        description="Max output tokens for the distillation stage",
    )

    # --- Reason Stage ---
    REASON_MODEL: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Model used for the reasoning stage",
    )
    REASON_TEMPERATURE: float = Field(
        default=0.0,
        description="Temperature for the reasoning stage",
    )
    REASON_MAX_TOKENS: int = Field(
        default=4096,
        description="Max output tokens for the reasoning stage",
    )

    # --- Validate Stage ---
    VALIDATE_MODEL: str = Field(
        default="gemini-2.5-flash",
        description="Model used for the validation stage",
    )
    VALIDATE_TEMPERATURE: float = Field(
        default=0.0,
        description="Temperature for the validation stage",
    )
    VALIDATE_MAX_TOKENS: int = Field(
        default=2048,
        description="Max output tokens for the validation stage",
    )

    # --- Validation / Agentic Limits ---
    VALIDATION_CONFIDENCE_THRESHOLD: float = Field(
        default=0.6,
        description="Minimum confidence score for a finding to pass validation",
    )
    MAX_AGENTIC_SCRIPTS_PER_FILE: int = Field(
        default=3,
        description="Maximum number of agentic verification scripts per file",
    )
    ENSEMBLE_MAX_RETRIES: int = Field(
        default=2,
        description="Maximum retries for ensemble pipeline stage failures",
    )

    # --- Derived helpers ---

    @property
    def is_ensemble_enabled(self) -> bool:
        """Returns True when the pipeline is running in ensemble mode."""
        return self.REVIEW_MODE == "ensemble"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton instance
_pipeline_settings: Optional[PipelineSettings] = None


def get_pipeline_settings() -> PipelineSettings:
    """Returns a singleton PipelineSettings instance."""
    global _pipeline_settings
    if _pipeline_settings is None:
        _pipeline_settings = PipelineSettings()
    return _pipeline_settings
