"""
Review Pipeline — Ensemble Multi-Model Review Orchestrator.

This is the central orchestrator for DevAssist-AI v3.0's review pipeline.
It supports two modes:

    Fast Mode (REVIEW_MODE=fast):
        Single-model review, identical to v2.0 behavior.
        One LLM call per file using the configured model.

    Ensemble Mode (REVIEW_MODE=ensemble):
        Three-stage pipeline using multiple specialized models:
        Stage 1 (Distill):  Fast model compresses context into a digest
        Stage 2 (Reason):   Powerful model finds bugs and generates fixes
        Stage 3 (Validate): Fast model verifies findings and scores confidence

Design Principles:
    - Backward compatible: fast mode is the default, existing behavior unchanged
    - Graceful degradation: if any stage fails, pipeline continues with best effort
    - Cost-aware: tracks tokens and cost per stage
    - Thread-safe: no shared mutable state between calls
"""

import json
import re
import time
from typing import Optional

from core.logger import get_logger, generate_request_id
from core.pipeline_config import get_pipeline_settings
from llm.router import LLMRouter
from llm.schemas import LLMRequest, LLMResponse
from llm.pipeline_schemas import (
    DistillationResult,
    ValidatedFinding,
    PipelineResult,
    StageResult,
)
from llm.context_distiller import ContextDistiller
from llm.finding_validator import FindingValidator
from llm.metrics import estimate_cost
from prompts import load_prompt

logger = get_logger("llm.pipeline")


class ReviewPipeline:
    """Ensemble multi-model review pipeline with fast mode fallback.

    Orchestrates up to three LLM stages to review code changes. In fast mode,
    it behaves identically to the v2.0 single-model approach. In ensemble mode,
    it compresses context, performs deep reasoning, and validates findings.

    Usage:
        pipeline = ReviewPipeline(router)
        result = pipeline.run(
            file_data={"filename": "utils.py", "patch": "...", "status": "modified", ...},
            system_prompt="...",
            context="RAG context...",
            lint_result="pylint output...",
            impact_report={"blast_radius": "HIGH", ...},
        )

    Attributes:
        mode: Current pipeline mode ('fast' or 'ensemble').
        router: The LLMRouter instance for making LLM calls.
        distiller: ContextDistiller for Stage 1 (ensemble only).
        validator: FindingValidator for Stage 3 (ensemble only).
    """

    def __init__(self, router: LLMRouter, mode: Optional[str] = None):
        """Initialize the review pipeline.

        Args:
            router: The shared LLMRouter instance.
            mode: Override pipeline mode ('fast' or 'ensemble').
                  If None, reads from REVIEW_MODE env var.
        """
        self.router = router
        self.pipeline_settings = get_pipeline_settings()
        self.mode = mode or self.pipeline_settings.REVIEW_MODE

        # Initialize ensemble components (lazy — only used if mode == 'ensemble')
        self._distiller: Optional[ContextDistiller] = None
        self._validator: Optional[FindingValidator] = None

    @property
    def distiller(self) -> ContextDistiller:
        """Lazy-initialized context distiller for Stage 1."""
        if self._distiller is None:
            self._distiller = ContextDistiller(self.router)
        return self._distiller

    @property
    def validator(self) -> FindingValidator:
        """Lazy-initialized finding validator for Stage 3."""
        if self._validator is None:
            self._validator = FindingValidator(self.router)
        return self._validator

    def run(
        self,
        file_data: dict,
        system_prompt: str,
        context: str = "",
        lint_result: str = "",
        impact_report: Optional[dict] = None,
        request_id: str = "",
        pr_number: int = 0,
    ) -> PipelineResult:
        """Execute the configured pipeline mode for a single file.

        Args:
            file_data: Dict with keys: filename, patch, status, additions, deletions.
            system_prompt: The system prompt for the review LLM call.
            context: RAG-retrieved codebase context.
            lint_result: Formatted linter output for this file.
            impact_report: CodeGraph impact analysis dict (optional).
            request_id: Request ID for tracing.
            pr_number: PR number for metadata.

        Returns:
            PipelineResult with validated findings, stage metadata, and cost info.
        """
        if not request_id:
            request_id = generate_request_id()

        start_time = time.time()

        if self.mode == "ensemble":
            result = self._run_ensemble(
                file_data=file_data,
                system_prompt=system_prompt,
                context=context,
                lint_result=lint_result,
                impact_report=impact_report,
                request_id=request_id,
                pr_number=pr_number,
            )
        else:
            result = self._run_fast(
                file_data=file_data,
                system_prompt=system_prompt,
                context=context,
                lint_result=lint_result,
                request_id=request_id,
                pr_number=pr_number,
            )

        result.duration_seconds = round(time.time() - start_time, 2)
        return result

    # ─── Fast Mode ────────────────────────────────────────────────────────

    def _run_fast(
        self,
        file_data: dict,
        system_prompt: str,
        context: str,
        lint_result: str,
        request_id: str,
        pr_number: int,
    ) -> PipelineResult:
        """Single-model review — v2.0 compatible behavior.

        Makes one LLM call per file using the configured model and existing
        review prompt. Output is parsed into ValidatedFinding objects for
        uniform handling downstream.
        """
        filename = file_data.get("filename", "unknown")
        patch = file_data.get("patch", "")

        logger.info(f"[{request_id}] Fast mode review: {filename}")

        # Build user content (same format as v2.0 review_agent._review_single_file)
        user_content = (
            f"Review the changes in this file and provide inline comments:\n\n"
            f"File: {filename}\n"
            f"Status: {file_data.get('status', 'modified')}\n\n"
            f"{patch}"
        )
        if context:
            user_content += f"\n\n--- Codebase Context ---\n{context}"
        if lint_result:
            user_content += f"\n\n--- Linter Results ---\n{lint_result}"

        llm_request = LLMRequest(
            task_type="code_review",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=self.pipeline_settings.REASON_TEMPERATURE,
            metadata={
                "request_id": request_id,
                "pr_number": pr_number,
                "file": filename,
                "pipeline_stage": "fast_review",
            },
        )

        llm_response = self.router.generate(llm_request)

        # Build result
        result = PipelineResult(
            mode="fast",
            model_used=llm_response.model,
            provider_used=llm_response.provider,
            total_tokens_input=llm_response.tokens_input,
            total_tokens_output=llm_response.tokens_output,
            total_cost_estimate=estimate_cost(
                llm_response.model,
                llm_response.tokens_input,
                llm_response.tokens_output,
            ),
        )

        if not llm_response.success:
            result.errors.append(f"LLM call failed: {llm_response.error}")
            return result

        result.stages_completed.append("fast_review")

        # Debug: log raw LLM output for diagnosis
        logger.info(
            f"[{request_id}] Raw LLM output (first 500 chars): "
            f"{llm_response.content[:500] if llm_response.content else '(empty)'}"
        )

        # Parse findings from LLM output (reuse v2.0 parsing logic)
        raw_findings = self._parse_review_output(llm_response.content, filename)
        logger.info(f"[{request_id}] Parsed {len(raw_findings)} findings from LLM output")

        # Convert to ValidatedFinding (confidence=1.0, unvalidated in fast mode)
        for finding in raw_findings:
            result.findings.append(
                ValidatedFinding(
                    file=finding.get("file", filename),
                    line=int(finding.get("line", 0)),
                    severity=finding.get("severity", "suggestion"),
                    category=finding.get("category", "unknown"),
                    comment=finding.get("comment", ""),
                    code_fix=finding.get("code_fix"),
                    confidence=1.0,  # No validation in fast mode
                    tool_source="fast_review",
                )
            )

        return result

    # ─── Ensemble Mode ────────────────────────────────────────────────────

    def _run_ensemble(
        self,
        file_data: dict,
        system_prompt: str,
        context: str,
        lint_result: str,
        impact_report: Optional[dict],
        request_id: str,
        pr_number: int,
    ) -> PipelineResult:
        """Three-stage ensemble pipeline: distill → reason → validate.

        Stage 1 (Distill): Fast model compresses raw inputs into a digest.
        Stage 2 (Reason): Powerful model performs deep analysis.
        Stage 3 (Validate): Fast model verifies and scores findings.
        """
        filename = file_data.get("filename", "unknown")
        patch = file_data.get("patch", "")

        logger.info(f"[{request_id}] Ensemble mode review: {filename}")

        result = PipelineResult(mode="ensemble")
        total_tokens_in = 0
        total_tokens_out = 0
        total_cost = 0.0

        # ── Stage 1: Distill ──────────────────────────────────────────────

        logger.info(f"[{request_id}] Stage 1: Distilling context for {filename}")

        distillation, distill_stage = self.distiller.distill(
            diff=patch,
            filename=filename,
            context=context,
            lint_findings=lint_result,
            impact_report=impact_report,
            request_id=request_id,
        )

        result.distillation = distillation
        total_tokens_in += distill_stage.tokens_input
        total_tokens_out += distill_stage.tokens_output

        if distill_stage.success:
            result.stages_completed.append("distill")
            distill_stage.cost_estimate = estimate_cost(
                distill_stage.model,
                distill_stage.tokens_input,
                distill_stage.tokens_output,
            )
            total_cost += distill_stage.cost_estimate
        else:
            result.errors.append(f"Distillation failed: {distill_stage.error}")
            # Continue anyway — distiller provides fallback

        logger.info(
            f"[{request_id}] Distill complete: type={distillation.change_type}, "
            f"risks={distillation.risk_areas}, complexity={distillation.estimated_complexity}"
        )

        # ── Stage 2: Reason ───────────────────────────────────────────────

        logger.info(f"[{request_id}] Stage 2: Deep reasoning for {filename}")

        raw_findings, reason_stage = self._run_reasoning(
            file_data=file_data,
            system_prompt=system_prompt,
            distillation=distillation,
            patch=patch,
            lint_result=lint_result,
            request_id=request_id,
            pr_number=pr_number,
        )

        total_tokens_in += reason_stage.tokens_input
        total_tokens_out += reason_stage.tokens_output

        if reason_stage.success:
            result.stages_completed.append("reason")
            reason_stage.cost_estimate = estimate_cost(
                reason_stage.model,
                reason_stage.tokens_input,
                reason_stage.tokens_output,
            )
            total_cost += reason_stage.cost_estimate
            result.model_used = reason_stage.model
            result.provider_used = reason_stage.provider
        else:
            result.errors.append(f"Reasoning failed: {reason_stage.error}")
            # No findings to validate — return what we have
            result.total_tokens_input = total_tokens_in
            result.total_tokens_output = total_tokens_out
            result.total_cost_estimate = round(total_cost, 6)
            return result

        logger.info(
            f"[{request_id}] Reasoning complete: {len(raw_findings)} findings "
            f"({reason_stage.model}, {reason_stage.latency_seconds:.1f}s)"
        )

        # ── Stage 3: Validate ─────────────────────────────────────────────

        if not raw_findings:
            logger.info(f"[{request_id}] No findings to validate — clean review")
            result.stages_completed.append("validate")
            result.total_tokens_input = total_tokens_in
            result.total_tokens_output = total_tokens_out
            result.total_cost_estimate = round(total_cost, 6)
            return result

        logger.info(
            f"[{request_id}] Stage 3: Validating {len(raw_findings)} findings "
            f"for {filename}"
        )

        validated_findings, validate_stage = self.validator.validate(
            raw_findings=raw_findings,
            file_patch=patch,
            filename=filename,
            request_id=request_id,
        )

        total_tokens_in += validate_stage.tokens_input
        total_tokens_out += validate_stage.tokens_output

        if validate_stage.success:
            result.stages_completed.append("validate")
            validate_stage.cost_estimate = estimate_cost(
                validate_stage.model,
                validate_stage.tokens_input,
                validate_stage.tokens_output,
            )
            total_cost += validate_stage.cost_estimate
        else:
            result.errors.append(f"Validation failed: {validate_stage.error}")
            # Findings were passed through unfiltered by the validator

        result.findings = validated_findings
        result.total_tokens_input = total_tokens_in
        result.total_tokens_output = total_tokens_out
        result.total_cost_estimate = round(total_cost, 6)

        logger.info(
            f"[{request_id}] Ensemble complete for {filename}: "
            f"{len(validated_findings)} validated findings, "
            f"cost=${total_cost:.4f}, "
            f"stages={result.stages_completed}"
        )

        return result

    def _run_reasoning(
        self,
        file_data: dict,
        system_prompt: str,
        distillation: DistillationResult,
        patch: str,
        lint_result: str,
        request_id: str,
        pr_number: int,
    ) -> tuple[list[dict], StageResult]:
        """Execute Stage 2: Deep reasoning using the powerful model.

        Builds an enriched prompt that includes the distillation digest,
        the original patch, and key concerns for the model to investigate.

        Returns:
            Tuple of (raw_findings_list, stage_result).
        """
        start_time = time.time()
        filename = file_data.get("filename", "unknown")

        # Build the enriched reasoning prompt
        user_content = self._build_reasoning_prompt(
            file_data=file_data,
            distillation=distillation,
            patch=patch,
            lint_result=lint_result,
        )

        llm_request = LLMRequest(
            task_type="code_review",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=self.pipeline_settings.REASON_TEMPERATURE,
            max_tokens=self.pipeline_settings.REASON_MAX_TOKENS,
            metadata={
                "request_id": request_id,
                "pr_number": pr_number,
                "file": filename,
                "model": self.pipeline_settings.REASON_MODEL,
                "pipeline_stage": "reason",
            },
        )

        llm_response = self.router.generate(llm_request)
        elapsed = time.time() - start_time

        stage_result = StageResult(
            stage_name="reason",
            model=llm_response.model,
            provider=llm_response.provider,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            latency_seconds=round(elapsed, 2),
            success=llm_response.success,
            error=llm_response.error,
            raw_output=llm_response.content if llm_response.success else "",
        )

        if not llm_response.success:
            return [], stage_result

        # Parse the reasoning output
        findings = self._parse_review_output(llm_response.content, filename)
        return findings, stage_result

    def _build_reasoning_prompt(
        self,
        file_data: dict,
        distillation: DistillationResult,
        patch: str,
        lint_result: str,
    ) -> str:
        """Build the enriched prompt for the reasoning model.

        Combines the compressed digest from Stage 1 with the original patch,
        guiding the reasoning model to focus on identified risk areas.
        """
        filename = file_data.get("filename", "unknown")
        parts = []

        # Include the distillation digest
        parts.append("## Pre-Analysis Summary (from context distillation):")
        parts.append(f"- **Change Type**: {distillation.change_type}")
        parts.append(f"- **Complexity**: {distillation.estimated_complexity}")
        if distillation.risk_areas:
            parts.append(f"- **Risk Areas**: {', '.join(distillation.risk_areas)}")
        parts.append(f"- **Summary**: {distillation.summary}")

        if distillation.key_concerns:
            parts.append("\n### Key Concerns to Investigate:")
            for i, concern in enumerate(distillation.key_concerns, 1):
                parts.append(f"  {i}. {concern}")

        # Include the actual file diff
        parts.append(f"\n## File: {filename}")
        parts.append(f"Status: {file_data.get('status', 'modified')}")
        parts.append(f"Additions: +{file_data.get('additions', 0)}")
        parts.append(f"Deletions: -{file_data.get('deletions', 0)}")
        parts.append("\n## Code Diff:")
        parts.append(patch)

        # Include lint findings if available
        if lint_result:
            parts.append("\n## Linter Findings:")
            parts.append(lint_result)

        # Closing instruction
        parts.append(
            "\n\nFocus your deep analysis on the risk areas and key concerns "
            "identified above. Provide findings following the output format "
            "specified in your system prompt."
        )

        return "\n".join(parts)

    # ─── Shared Parsing ───────────────────────────────────────────────────

    def _parse_review_output(self, output: str, filename: str) -> list[dict]:
        """Parse LLM review output into a list of finding dicts.

        Handles multiple output formats:
            - {"comments": [...]}
            - [...]
            - Markdown-fenced JSON
            - Mixed text with embedded JSON
        """
        cleaned = output.strip()
        # Remove markdown fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE)
        
        # Extract outermost JSON object/array to bypass conversational filler
        first_brace = cleaned.find('{')
        first_bracket = cleaned.find('[')
        start_idx = -1
        end_idx = -1
        
        if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
            start_idx = first_brace
            end_idx = cleaned.rfind('}')
        elif first_bracket != -1:
            start_idx = first_bracket
            end_idx = cleaned.rfind(']')
            
        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            cleaned = cleaned[start_idx:end_idx+1]

        comments = []
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and "comments" in parsed:
                comments = parsed["comments"]
            elif isinstance(parsed, list):
                comments = parsed
            else:
                return []
        except json.JSONDecodeError:
            return []

        # Normalize and validate each finding
        valid_findings = []
        if isinstance(comments, list):
            for c in comments:
                if not isinstance(c, dict) or "line" not in c:
                    continue

                # Normalize "message" + "suggestion" → "comment" (local prompt format)
                if "message" in c and "comment" not in c:
                    cat = c.get("category", "")
                    msg = c.get("message", "")
                    sug = c.get("suggestion", "")

                    full_comment = msg
                    if sug:
                        full_comment += f"\n\n**Suggestion:** {sug}"
                    if cat:
                        full_comment = f"**[{cat.upper()}]** {full_comment}"

                    c["comment"] = full_comment

                if "comment" in c:
                    c.setdefault("file", filename)
                    valid_findings.append(c)

        return valid_findings
