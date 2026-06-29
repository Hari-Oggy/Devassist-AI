"""
Finding Validator — Stage 3 of the Ensemble Review Pipeline.

Receives raw findings from the reasoning stage (Stage 2) and validates each one
against the actual code diff using a fast model. Scores confidence, flags false
positives, and deduplicates overlapping comments.

Design:
    - Uses the fast model configured via VALIDATE_MODEL (e.g., Gemini Flash)
    - Filters out findings below VALIDATION_CONFIDENCE_THRESHOLD
    - Removes duplicates by (file, line, similar_comment)
    - Gracefully degrades: returns all findings unfiltered if validation fails
"""

import json
import re
import time
from typing import Optional

from core.logger import get_logger
from core.pipeline_config import get_pipeline_settings
from llm.router import LLMRouter
from llm.schemas import LLMRequest
from llm.pipeline_schemas import ValidatedFinding, StageResult
from prompts import load_prompt

logger = get_logger("llm.finding_validator")


class FindingValidator:
    """Validates and scores findings from the reasoning stage.

    Uses a fast model to cross-check each finding against the actual diff,
    scoring confidence and removing false positives. This is Stage 3 of the
    ensemble pipeline.

    The validator checks:
        1. Line number accuracy (is it a changed line in the diff?)
        2. Issue validity (is it real or speculative?)
        3. Code fix correctness (is the suggested fix syntactically valid?)
        4. Comment quality (does it explain WHY with real-world impact?)
        5. Deduplication (are there overlapping findings?)

    Usage:
        validator = FindingValidator(router)
        validated = validator.validate(raw_findings, file_patch)
    """

    def __init__(self, router: LLMRouter):
        """Initialize with the shared LLM router.

        Args:
            router: The LLMRouter instance for making LLM calls.
        """
        self.router = router
        self.pipeline_settings = get_pipeline_settings()

    def validate(
        self,
        raw_findings: list[dict],
        file_patch: str,
        filename: str = "",
        request_id: str = "",
    ) -> tuple[list[ValidatedFinding], StageResult]:
        """Validate findings from the reasoning stage.

        Args:
            raw_findings: List of finding dicts from Stage 2 (with file, line,
                severity, category, comment, code_fix fields).
            file_patch: The original diff/patch for the file being reviewed.
            filename: Name of the file being reviewed.
            request_id: Request ID for tracing.

        Returns:
            Tuple of (validated_findings, stage_result) where validated_findings
            only contains findings above the confidence threshold.
        """
        start_time = time.time()

        # If no findings to validate, return early
        if not raw_findings:
            return [], StageResult(
                stage_name="validate",
                model="skipped",
                provider="skipped",
                success=True,
                raw_output="No findings to validate.",
            )

        # Build the validation prompt
        user_content = self._build_validation_prompt(raw_findings, file_patch, filename)

        # Load the validation system prompt
        try:
            system_prompt = load_prompt("validate_prompt")
        except FileNotFoundError:
            logger.warning("validate_prompt.txt not found, using fallback prompt")
            system_prompt = self._fallback_system_prompt()

        # Build LLM request targeting the validate model
        llm_request = LLMRequest(
            task_type="finding_validation",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=self.pipeline_settings.VALIDATE_TEMPERATURE,
            max_tokens=self.pipeline_settings.VALIDATE_MAX_TOKENS,
            metadata={
                "request_id": request_id,
                "model": self.pipeline_settings.VALIDATE_MODEL,
                "pipeline_stage": "validate",
            },
        )

        # Call the LLM
        llm_response = self.router.generate(llm_request)
        elapsed = time.time() - start_time

        # Build stage result metadata
        stage_result = StageResult(
            stage_name="validate",
            model=llm_response.model,
            provider=llm_response.provider,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            latency_seconds=round(elapsed, 2),
            success=llm_response.success,
            error=llm_response.error,
            raw_output=llm_response.content if llm_response.success else "",
        )

        if llm_response.success:
            validated = self._parse_validation(
                llm_response.content, raw_findings, filename
            )
        else:
            logger.warning(
                f"Validation LLM call failed: {llm_response.error}. "
                "Returning all findings unfiltered."
            )
            validated = self._pass_through_findings(raw_findings, filename)

        # Deduplicate after validation
        validated = self._deduplicate_findings(validated)

        return validated, stage_result

    def _build_validation_prompt(
        self, findings: list[dict], file_patch: str, filename: str
    ) -> str:
        """Build the user message for the validation LLM call."""
        parts = []

        parts.append(f"## File: {filename}")
        parts.append("")
        parts.append("## Original Diff:")
        parts.append("```")
        # Truncate very long diffs for the validator
        if len(file_patch) > 8000:
            parts.append(file_patch[:8000])
            parts.append(f"\n... [truncated, {len(file_patch) - 8000} chars omitted]")
        else:
            parts.append(file_patch)
        parts.append("```")
        parts.append("")
        parts.append(f"## Findings to Validate ({len(findings)} total):")
        parts.append("")

        for i, finding in enumerate(findings):
            parts.append(f"### Finding {i}:")
            parts.append(f"- **File**: {finding.get('file', filename)}")
            parts.append(f"- **Line**: {finding.get('line', '?')}")
            parts.append(f"- **Severity**: {finding.get('severity', 'suggestion')}")
            parts.append(f"- **Category**: {finding.get('category', 'unknown')}")
            parts.append(f"- **Comment**: {finding.get('comment', '')}")
            code_fix = finding.get("code_fix")
            if code_fix:
                parts.append(f"- **Suggested Fix**: `{code_fix}`")
            parts.append("")

        return "\n".join(parts)

    def _parse_validation(
        self,
        raw_output: str,
        original_findings: list[dict],
        filename: str,
    ) -> list[ValidatedFinding]:
        """Parse the validation LLM output and merge with original findings."""
        cleaned = raw_output.strip()
        # Remove markdown fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE)
        
        # Extract outermost JSON array
        first_bracket = cleaned.find('[')
        last_bracket = cleaned.rfind(']')
        if first_bracket != -1 and last_bracket != -1 and last_bracket >= first_bracket:
            cleaned = cleaned[first_bracket:last_bracket+1]

        try:
            validation_results = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Failed to parse validation JSON output")
            return self._pass_through_findings(original_findings, filename)

        if not isinstance(validation_results, list):
            logger.warning("Validation output is not a JSON array")
            return self._pass_through_findings(original_findings, filename)

        # Merge validation results with original findings
        threshold = self.pipeline_settings.VALIDATION_CONFIDENCE_THRESHOLD
        validated_findings = []

        for vr in validation_results:
            if not isinstance(vr, dict):
                continue

            idx = vr.get("original_index")
            if idx is None or not isinstance(idx, int):
                continue
            if idx < 0 or idx >= len(original_findings):
                continue

            confidence = float(vr.get("confidence", 0.5))
            is_valid = vr.get("is_valid", True)

            # Skip findings below threshold or explicitly marked invalid
            if not is_valid or confidence < threshold:
                logger.info(
                    f"Filtered finding {idx}: confidence={confidence:.2f}, "
                    f"valid={is_valid}, threshold={threshold}"
                )
                continue

            original = original_findings[idx]

            # Use corrected values if provided by the validator
            line = vr.get("corrected_line") or original.get("line", 0)
            comment = vr.get("corrected_comment") or original.get("comment", "")

            validated_findings.append(
                ValidatedFinding(
                    file=original.get("file", filename),
                    line=int(line),
                    severity=original.get("severity", "suggestion"),
                    category=original.get("category", "unknown"),
                    comment=comment,
                    code_fix=original.get("code_fix"),
                    confidence=round(confidence, 2),
                    tool_source="ensemble_reason",
                    validation_notes=vr.get("validation_notes", ""),
                )
            )

        logger.info(
            f"Validation: {len(validated_findings)}/{len(original_findings)} findings "
            f"passed (threshold={threshold})"
        )
        return validated_findings

    def _pass_through_findings(
        self, findings: list[dict], filename: str
    ) -> list[ValidatedFinding]:
        """Convert raw findings to ValidatedFinding without LLM validation.

        Used as fallback when the validation LLM call fails.
        All findings get a default confidence of 0.7.
        """
        validated = []
        for finding in findings:
            validated.append(
                ValidatedFinding(
                    file=finding.get("file", filename),
                    line=int(finding.get("line", 0)),
                    severity=finding.get("severity", "suggestion"),
                    category=finding.get("category", "unknown"),
                    comment=finding.get("comment", ""),
                    code_fix=finding.get("code_fix"),
                    confidence=0.7,  # Default confidence for unvalidated findings
                    tool_source="ensemble_reason",
                    validation_notes="Validation stage skipped (LLM call failed). Default confidence assigned.",
                )
            )
        return validated

    def _deduplicate_findings(
        self, findings: list[ValidatedFinding]
    ) -> list[ValidatedFinding]:
        """Remove duplicate findings that target the same file+line with similar comments.

        When duplicates are found, keep the one with higher confidence.
        Two findings are considered duplicates if they have the same file and line,
        and their comments share significant overlap (>60% word overlap).
        """
        if len(findings) <= 1:
            return findings

        # Sort by confidence descending so higher-confidence findings are kept first
        sorted_findings = sorted(findings, key=lambda f: f.confidence, reverse=True)
        unique: list[ValidatedFinding] = []
        seen_keys: set[tuple[str, int]] = set()

        for finding in sorted_findings:
            key = (finding.file, finding.line)

            if key in seen_keys:
                # Check word overlap with existing findings at this location
                is_duplicate = False
                for existing in unique:
                    if existing.file == finding.file and existing.line == finding.line:
                        overlap = self._word_overlap(existing.comment, finding.comment)
                        if overlap > 0.5:
                            is_duplicate = True
                            break
                if is_duplicate:
                    continue

            seen_keys.add(key)
            unique.append(finding)

        if len(unique) < len(findings):
            logger.info(
                f"Deduplication: removed {len(findings) - len(unique)} duplicate findings"
            )

        return unique

    @staticmethod
    def _word_overlap(text_a: str, text_b: str) -> float:
        """Calculate word-level Jaccard similarity between two texts."""
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    @staticmethod
    def _fallback_system_prompt() -> str:
        """Return a minimal fallback system prompt if validate_prompt.txt is missing."""
        return (
            "You are a code review QA specialist. You receive findings from an AI "
            "reviewer and must validate each one. For each finding, output a JSON "
            "object with: original_index (int), confidence (0.0-1.0), is_valid (bool), "
            "validation_notes (string). Output a JSON array. No markdown."
        )
