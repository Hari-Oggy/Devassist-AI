"""
Context Distiller — Stage 1 of the Ensemble Review Pipeline.

Compresses raw review inputs (diff, RAG context, lint findings, CodeGraph impact)
into a token-efficient structured digest using a fast LLM model.
The compressed digest is then passed to the expensive reasoning model (Stage 2),
saving cost and improving focus.

Design:
    - Uses the fast model configured via DISTILL_MODEL (e.g., Gemini Flash)
    - Manages token budgets per section to prevent context overflow
    - Produces a DistillationResult with change classification and key concerns
    - Gracefully degrades: returns a basic digest if LLM call fails
"""

import json
import re
import time
from typing import Optional

from core.logger import get_logger
from core.pipeline_config import get_pipeline_settings
from llm.router import LLMRouter
from llm.schemas import LLMRequest, LLMResponse
from llm.pipeline_schemas import DistillationResult, StageResult
from prompts import load_prompt

logger = get_logger("llm.context_distiller")


# Token budget limits for each context section
_MAX_DIFF_TOKENS = 6000
_MAX_RAG_TOKENS = 1500
_MAX_LINT_TOKENS = 800
_MAX_IMPACT_TOKENS = 500


def _truncate_to_budget(text: str, max_chars: int) -> str:
    """Truncate text to approximate token budget (1 token ≈ 4 chars)."""
    max_chars_approx = max_chars * 4
    if len(text) <= max_chars_approx:
        return text
    return text[:max_chars_approx] + f"\n\n... [truncated, {len(text) - max_chars_approx} chars omitted]"


def _format_lint_findings(lint_result: str, max_chars: int = _MAX_LINT_TOKENS * 4) -> str:
    """Format and truncate lint findings for inclusion in the distillation prompt."""
    if not lint_result:
        return "No linter findings."
    truncated = _truncate_to_budget(lint_result, _MAX_LINT_TOKENS)
    return truncated


def _format_impact_report(impact_report: Optional[dict]) -> str:
    """Format CodeGraph impact report for inclusion in the distillation prompt."""
    if not impact_report:
        return "No cross-file impact analysis available."
    
    parts = []
    blast_radius = impact_report.get("blast_radius", "UNKNOWN")
    parts.append(f"Blast Radius: {blast_radius}")
    
    high_risk = impact_report.get("high_risk_changes", [])
    if high_risk:
        parts.append("High-Risk Changes:")
        for change in high_risk[:5]:  # Cap at 5 entries
            func = change.get("function", "unknown")
            callers = change.get("callers_count", 0)
            parts.append(f"  - {func} (used by {callers} callers)")
    
    breaking = impact_report.get("breaking_changes", [])
    if breaking:
        parts.append("Breaking Changes:")
        for bc in breaking[:5]:
            parts.append(f"  - {bc.get('type', '?')}: {bc.get('function', '?')}")
    
    affected = impact_report.get("affected_files", [])
    if affected:
        parts.append(f"Affected Files ({len(affected)}): {', '.join(affected[:10])}")
    
    result = "\n".join(parts)
    return _truncate_to_budget(result, _MAX_IMPACT_TOKENS)


class ContextDistiller:
    """Compresses raw review inputs into a token-efficient digest for the reasoning stage.

    Uses a fast model (e.g., Gemini Flash) to analyze the raw diff, RAG context,
    lint findings, and CodeGraph impact report, producing a structured JSON digest
    that captures the essential information in ~2K tokens.

    The digest includes:
        - change_type: Classification of the PR change
        - risk_areas: Identified risk categories
        - summary: Condensed description of what changed and why
        - key_concerns: Specific questions for the reasoning model
        - estimated_complexity: How complex the changes are

    Usage:
        distiller = ContextDistiller(router)
        result = distiller.distill(
            diff="...", context="...", lint_findings="...", impact_report={...}
        )
    """

    def __init__(self, router: LLMRouter):
        """Initialize with the shared LLM router.

        Args:
            router: The LLMRouter instance for making LLM calls.
        """
        self.router = router
        self.pipeline_settings = get_pipeline_settings()

    def distill(
        self,
        diff: str,
        filename: str = "",
        context: str = "",
        lint_findings: str = "",
        impact_report: Optional[dict] = None,
        request_id: str = "",
    ) -> tuple[DistillationResult, StageResult]:
        """Compress raw review inputs into a structured digest.

        Args:
            diff: The raw unified diff for the file being reviewed.
            filename: Name of the file being reviewed.
            context: RAG-retrieved codebase context.
            lint_findings: Formatted linter output.
            impact_report: CodeGraph impact analysis dict (optional).
            request_id: Request ID for tracing.

        Returns:
            Tuple of (DistillationResult, StageResult) with the compressed digest
            and metadata about the LLM call.
        """
        start_time = time.time()

        # Build the user message with budget-managed sections
        user_content = self._build_user_message(
            diff=diff,
            filename=filename,
            context=context,
            lint_findings=lint_findings,
            impact_report=impact_report,
        )

        # Load the distillation system prompt
        try:
            system_prompt = load_prompt("distill_prompt")
        except FileNotFoundError:
            logger.warning("distill_prompt.txt not found, using fallback prompt")
            system_prompt = self._fallback_system_prompt()

        # Build LLM request targeting the distill model
        llm_request = LLMRequest(
            task_type="context_distillation",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=self.pipeline_settings.DISTILL_TEMPERATURE,
            max_tokens=self.pipeline_settings.DISTILL_MAX_TOKENS,
            metadata={
                "request_id": request_id,
                "model": self.pipeline_settings.DISTILL_MODEL,
                "pipeline_stage": "distill",
            },
        )

        # Call the LLM
        llm_response = self.router.generate(llm_request)
        elapsed = time.time() - start_time

        # Build stage result metadata
        stage_result = StageResult(
            stage_name="distill",
            model=llm_response.model,
            provider=llm_response.provider,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            latency_seconds=round(elapsed, 2),
            success=llm_response.success,
            error=llm_response.error,
            raw_output=llm_response.content if llm_response.success else "",
        )

        # Parse the distillation output
        if llm_response.success:
            distillation = self._parse_distillation(
                llm_response.content, llm_response, elapsed
            )
        else:
            logger.warning(
                f"Distillation LLM call failed: {llm_response.error}. Using basic fallback."
            )
            distillation = self._fallback_distillation(diff, filename)

        return distillation, stage_result

    def _build_user_message(
        self,
        diff: str,
        filename: str,
        context: str,
        lint_findings: str,
        impact_report: Optional[dict],
    ) -> str:
        """Build the user message with token-budget-managed sections."""
        parts = []

        if filename:
            parts.append(f"## File: {filename}")

        parts.append("## Code Diff:")
        parts.append(_truncate_to_budget(diff, _MAX_DIFF_TOKENS))

        if context:
            parts.append("\n## Codebase Context (RAG):")
            parts.append(_truncate_to_budget(context, _MAX_RAG_TOKENS))

        if lint_findings:
            parts.append("\n## Linter Findings:")
            parts.append(_format_lint_findings(lint_findings))

        parts.append("\n## Cross-File Impact Analysis:")
        parts.append(_format_impact_report(impact_report))

        return "\n".join(parts)

    def _parse_distillation(
        self, raw_output: str, llm_response: LLMResponse, elapsed: float
    ) -> DistillationResult:
        """Parse the LLM's distillation output into a structured DistillationResult."""
        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw_output)
        cleaned = re.sub(r"```\s*$", "", cleaned.strip()).strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to extract JSON from surrounding text
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    logger.warning("Failed to parse distillation JSON output")
                    return self._fallback_distillation("", "")
            else:
                logger.warning("No JSON found in distillation output")
                return self._fallback_distillation("", "")

        # Validate and normalize fields
        valid_change_types = {"refactor", "feature", "bugfix", "config", "test", "mixed"}
        change_type = parsed.get("change_type", "mixed").lower()
        if change_type not in valid_change_types:
            change_type = "mixed"

        valid_risk_areas = {
            "security", "concurrency", "api_contract", "data_integrity",
            "error_handling", "performance", "type_safety", "resource_management",
        }
        risk_areas = [
            r for r in parsed.get("risk_areas", [])
            if isinstance(r, str) and r.lower() in valid_risk_areas
        ]

        valid_complexity = {"low", "medium", "high"}
        complexity = parsed.get("estimated_complexity", "medium").lower()
        if complexity not in valid_complexity:
            complexity = "medium"

        return DistillationResult(
            change_type=change_type,
            risk_areas=risk_areas,
            summary=str(parsed.get("summary", "No summary available.")),
            key_concerns=[
                str(c) for c in parsed.get("key_concerns", []) if isinstance(c, str)
            ][:5],  # Cap at 5 concerns
            estimated_complexity=complexity,
            tokens_used=llm_response.tokens_input + llm_response.tokens_output,
            latency_seconds=round(elapsed, 2),
            model_used=llm_response.model,
        )

    def _fallback_distillation(self, diff: str, filename: str) -> DistillationResult:
        """Generate a basic distillation without LLM when the call fails."""
        # Simple heuristic-based classification
        has_security_keywords = any(
            kw in diff.lower()
            for kw in ["password", "secret", "token", "api_key", "auth", "sql", "inject", "eval", "exec"]
        )
        has_concurrency_keywords = any(
            kw in diff.lower()
            for kw in ["thread", "lock", "async", "await", "concurrent", "mutex", "semaphore"]
        )

        risk_areas = []
        if has_security_keywords:
            risk_areas.append("security")
        if has_concurrency_keywords:
            risk_areas.append("concurrency")

        return DistillationResult(
            change_type="mixed",
            risk_areas=risk_areas,
            summary=f"Changes to {filename or 'unknown file'}. Automatic distillation failed; raw diff passed to reasoning stage.",
            key_concerns=["Review all changes carefully — automatic context compression was unavailable."],
            estimated_complexity="medium",
            tokens_used=0,
            latency_seconds=0.0,
            model_used="fallback_heuristic",
        )

    @staticmethod
    def _fallback_system_prompt() -> str:
        """Return a minimal fallback system prompt if distill_prompt.txt is missing."""
        return (
            "You are a code change analyst. Analyze the provided diff and context, "
            "then output a JSON object with these fields: change_type (refactor/feature/"
            "bugfix/config/test/mixed), risk_areas (array of: security, concurrency, "
            "api_contract, data_integrity, error_handling, performance, type_safety, "
            "resource_management), summary (2-4 sentences), key_concerns (1-5 specific "
            "questions for a deep reviewer), estimated_complexity (low/medium/high). "
            "Output pure JSON only. No markdown. No explanation."
        )
