"""
Per-repo configuration — .devassist.yml loader.

Each repository can place a `.devassist.yml` file in its root to customise
review behaviour without touching the server config.  The worker reads this
file from the *cloned* repo path before running the pipeline.

Example .devassist.yml:
    review:
      mode: ensemble          # fast | ensemble
      skip_files:
        - "*.lock"
        - "migrations/"
      focus_areas:
        - security
        - correctness
      language_hints:
        - python
        - typescript
    custom_rules:
      - "Never use print() for logging, use the logger"
      - "All API endpoints must have rate limiting"

If the file is missing or cannot be parsed, the global Settings are used.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator
from core.pipeline_config import get_pipeline_settings 
from core.logger import get_logger

logger = get_logger("core.repo_config")

_FILENAME = ".devassist.yml"


# ── Schema ─────────────────────────────────────────────────────────────

class ReviewSection(BaseModel):
    """Settings under the ``review:`` key in .devassist.yml."""

    mode: str = Field(
        default_factory=lambda: get_pipeline_settings().REVIEW_MODE,
        description="Pipeline mode: 'fast' | 'ensemble'",
    )

    skip_files: list[str] = Field(
        default_factory=list,
        description="Glob patterns for files to skip during review",
    )
    focus_areas: list[str] = Field(
        default_factory=list,
        description="Review focus areas, e.g. ['security', 'correctness']",
    )
    language_hints: list[str] = Field(
        default_factory=list,
        description="Primary languages in this repo (helps with code-fix language detection)",
    )
    max_findings_per_file: int = Field(
        default=20,
        description="Cap findings per file to avoid overwhelming comments",
    )
    skip_draft_prs: Optional[bool] = Field(
        default=None,
        description="Override global SKIP_DRAFT_PRS setting for this repo",
    )

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in {"fast", "ensemble"}:
            logger.warning("Invalid review mode '%s' in .devassist.yml — falling back to 'fast'", v)
            return "fast"
        return v


class RepoConfig(BaseModel):
    """Top-level schema for .devassist.yml."""

    review: ReviewSection = Field(default_factory=ReviewSection)
    custom_rules: list[str] = Field(
        default_factory=list,
        description="Project-specific review rules injected into the LLM prompt",
    )
    notifications: dict[str, Any] = Field(
        default_factory=dict,
        description="Reserved for future notification hook config",
    )

    @property
    def has_custom_rules(self) -> bool:
        return bool(self.custom_rules)

    def format_custom_rules_prompt(self) -> str:
        """Format custom rules as a numbered list for LLM injection."""
        if not self.custom_rules:
            return ""
        lines = ["Project-specific rules that MUST be enforced:"]
        for i, rule in enumerate(self.custom_rules, 1):
            lines.append(f"  {i}. {rule}")
        return "\n".join(lines)

    def should_skip_file(self, filename: str) -> bool:
        """Return True if *filename* matches any skip_files glob pattern."""
        import fnmatch
        for pattern in self.review.skip_files:
            # Support both glob patterns and directory prefixes
            if fnmatch.fnmatch(filename, pattern):
                return True
            # Also check if the file is inside a skipped directory
            if pattern.endswith("/") and filename.startswith(pattern):
                return True
        return False


# ── Loader ─────────────────────────────────────────────────────────────

_DEFAULT_CONFIG = RepoConfig()


def load_repo_config(repo_path: str) -> RepoConfig:
    """Load and validate .devassist.yml from *repo_path*.

    Returns the parsed :class:`RepoConfig` on success, or the global
    default config if the file is absent, empty, or invalid.

    Args:
        repo_path: Absolute path to the cloned repository root.

    Returns:
        Validated :class:`RepoConfig` instance.
    """
    config_path = os.path.join(repo_path, _FILENAME)

    if not os.path.isfile(config_path):
        logger.debug("No .devassist.yml found in %s — using defaults", repo_path)
        return _DEFAULT_CONFIG

    try:
        import yaml  # PyYAML — already in dependencies

        with open(config_path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        if not raw or not isinstance(raw, dict):
            logger.warning(
                ".devassist.yml in %s is empty or not a mapping — using defaults", repo_path
            )
            return _DEFAULT_CONFIG

        config = RepoConfig(**raw)
        logger.info(
            "Loaded .devassist.yml from %s: mode=%s, custom_rules=%d, skip_files=%d",
            repo_path,
            config.review.mode,
            len(config.custom_rules),
            len(config.review.skip_files),
        )
        return config

    except Exception as exc:
        logger.warning(
            "Failed to parse .devassist.yml in %s (%s) — using defaults", repo_path, exc
        )
        return _DEFAULT_CONFIG
