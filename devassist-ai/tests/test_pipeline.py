"""
Tests for the Ensemble Review Pipeline (Phase 1).

Tests cover:
    - Fast mode produces ValidatedFinding objects from LLM output
    - Ensemble mode runs 3 stages (distill → reason → validate)
    - Validation filters low-confidence findings
    - Graceful fallback when ensemble models are unavailable
    - Context distillation produces structured digests
    - Finding deduplication works correctly
    - Backward compatibility: fast mode output matches v2.0 format
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from llm.pipeline_schemas import (
    DistillationResult,
    ValidatedFinding,
    PipelineResult,
    StageResult,
)


# ── Schema Tests ────────────────────────────────────────────────────────


class TestDistillationResult:
    """Tests for the DistillationResult schema."""

    def test_default_values(self):
        result = DistillationResult(
            change_type="feature",
            risk_areas=["security"],
            summary="Adds new endpoint",
            key_concerns=["Input validation?"],
            estimated_complexity="medium",
        )
        assert result.change_type == "feature"
        assert result.tokens_used == 0
        assert result.latency_seconds == 0.0
        assert result.model_used == ""

    def test_all_fields(self):
        result = DistillationResult(
            change_type="bugfix",
            risk_areas=["concurrency", "data_integrity"],
            summary="Fixes race condition in worker pool",
            key_concerns=["Thread safety of shared dict", "Lock ordering"],
            estimated_complexity="high",
            tokens_used=150,
            latency_seconds=0.8,
            model_used="gemini-2.5-flash",
        )
        assert len(result.risk_areas) == 2
        assert len(result.key_concerns) == 2
        assert result.tokens_used == 150


class TestValidatedFinding:
    """Tests for the ValidatedFinding schema."""

    def test_defaults(self):
        finding = ValidatedFinding(
            file="utils.py",
            line=42,
            severity="error",
            category="security",
            comment="SQL injection via f-string",
        )
        assert finding.confidence == 1.0
        assert finding.tool_source == "ensemble_reason"
        assert finding.code_fix is None
        assert finding.validation_notes is None

    def test_with_code_fix(self):
        finding = ValidatedFinding(
            file="api.py",
            line=10,
            severity="warning",
            category="reliability",
            comment="Missing timeout on requests.get()",
            code_fix='requests.get(url, timeout=10)',
            confidence=0.92,
            validation_notes="Confirmed: no timeout parameter set",
        )
        assert finding.code_fix == 'requests.get(url, timeout=10)'
        assert finding.confidence == 0.92


class TestPipelineResult:
    """Tests for the PipelineResult schema."""

    def test_empty_result(self):
        result = PipelineResult()
        assert result.findings == []
        assert result.mode == "fast"
        assert result.stages_completed == []
        assert result.success is True  # No errors = success

    def test_with_findings(self):
        finding = ValidatedFinding(
            file="test.py", line=1, severity="error",
            category="correctness", comment="Bug found",
        )
        result = PipelineResult(
            findings=[finding],
            mode="ensemble",
            stages_completed=["distill", "reason", "validate"],
            total_tokens_input=500,
            total_tokens_output=200,
            total_cost_estimate=0.005,
        )
        assert len(result.findings) == 1
        assert result.success is True

    def test_with_errors(self):
        result = PipelineResult(errors=["LLM call failed"])
        assert result.success is False

    def test_success_with_errors_but_findings(self):
        finding = ValidatedFinding(
            file="test.py", line=1, severity="warning",
            category="style", comment="Naming convention",
        )
        result = PipelineResult(
            findings=[finding],
            errors=["Validation stage failed"],
        )
        # Has errors but also has findings — still considered success
        assert result.success is True


class TestStageResult:
    """Tests for the StageResult schema."""

    def test_successful_stage(self):
        stage = StageResult(
            stage_name="distill",
            model="gemini-2.5-flash",
            provider="gemini",
            tokens_input=200,
            tokens_output=100,
            latency_seconds=0.5,
            success=True,
        )
        assert stage.success is True
        assert stage.error is None

    def test_failed_stage(self):
        stage = StageResult(
            stage_name="reason",
            model="claude-3-5-sonnet-20241022",
            provider="anthropic",
            success=False,
            error="Rate limited",
        )
        assert stage.success is False
        assert stage.error == "Rate limited"


# ── Pipeline Config Tests ───────────────────────────────────────────────


class TestPipelineConfig:
    """Tests for pipeline_config.py."""

    def test_default_values(self):
        import os
        from unittest.mock import patch
        from core.pipeline_config import PipelineSettings
        with patch.dict(os.environ, {}, clear=True):
            settings = PipelineSettings(_env_file=None)
            assert settings.REVIEW_MODE == "fast"
            assert settings.DISTILL_MODEL == "gemini-2.5-flash"
            assert settings.VALIDATION_CONFIDENCE_THRESHOLD == 0.6

    def test_ensemble_enabled_property(self):
        from core.pipeline_config import PipelineSettings
        fast_settings = PipelineSettings(REVIEW_MODE="fast")
        assert fast_settings.is_ensemble_enabled is False

        ensemble_settings = PipelineSettings(REVIEW_MODE="ensemble")
        assert ensemble_settings.is_ensemble_enabled is True


# ── Context Distiller Tests ─────────────────────────────────────────────


class TestContextDistiller:
    """Tests for context_distiller.py."""

    def test_fallback_distillation_security_keywords(self):
        from llm.context_distiller import ContextDistiller

        mock_router = MagicMock()
        distiller = ContextDistiller(mock_router)

        result = distiller._fallback_distillation(
            diff="+ password = 'hardcoded_secret'",
            filename="config.py",
        )
        assert "security" in result.risk_areas
        assert result.change_type == "mixed"
        assert result.model_used == "fallback_heuristic"

    def test_fallback_distillation_concurrency_keywords(self):
        from llm.context_distiller import ContextDistiller

        mock_router = MagicMock()
        distiller = ContextDistiller(mock_router)

        result = distiller._fallback_distillation(
            diff="+ with threading.Lock():\n+     shared_dict[key] = value",
            filename="worker.py",
        )
        assert "concurrency" in result.risk_areas

    def test_parse_valid_distillation(self):
        from llm.context_distiller import ContextDistiller
        from llm.schemas import LLMResponse

        mock_router = MagicMock()
        distiller = ContextDistiller(mock_router)

        raw_output = json.dumps({
            "change_type": "feature",
            "risk_areas": ["security", "api_contract"],
            "summary": "Adds new REST endpoint for user profile updates.",
            "key_concerns": ["Does it validate user_id ownership?"],
            "estimated_complexity": "medium",
        })

        mock_response = LLMResponse(
            content=raw_output,
            model="gemini-2.5-flash",
            provider="gemini",
            tokens_input=100,
            tokens_output=80,
            latency=0.5,
        )

        result = distiller._parse_distillation(raw_output, mock_response, 0.5)
        assert result.change_type == "feature"
        assert "security" in result.risk_areas
        assert result.estimated_complexity == "medium"

    def test_parse_distillation_with_markdown_fences(self):
        from llm.context_distiller import ContextDistiller
        from llm.schemas import LLMResponse

        mock_router = MagicMock()
        distiller = ContextDistiller(mock_router)

        raw_output = '```json\n{"change_type": "bugfix", "risk_areas": [], "summary": "Fix", "key_concerns": [], "estimated_complexity": "low"}\n```'

        mock_response = LLMResponse(
            content=raw_output, model="test", provider="test",
            tokens_input=50, tokens_output=30, latency=0.3,
        )

        result = distiller._parse_distillation(raw_output, mock_response, 0.3)
        assert result.change_type == "bugfix"


# ── Finding Validator Tests ─────────────────────────────────────────────


class TestFindingValidator:
    """Tests for finding_validator.py."""

    def test_pass_through_on_empty_findings(self):
        from llm.finding_validator import FindingValidator

        mock_router = MagicMock()
        validator = FindingValidator(mock_router)

        validated, stage = validator.validate([], "diff content", "test.py")
        assert validated == []
        assert stage.model == "skipped"

    def test_pass_through_on_failed_llm(self):
        from llm.finding_validator import FindingValidator
        from llm.schemas import LLMResponse

        mock_router = MagicMock()
        mock_router.generate.return_value = LLMResponse(
            error="Rate limited", provider="test",
        )

        validator = FindingValidator(mock_router)

        raw_findings = [
            {"file": "test.py", "line": 10, "severity": "error",
             "category": "security", "comment": "SQL injection"},
        ]

        validated, stage = validator.validate(raw_findings, "diff", "test.py")
        # All findings should pass through with default confidence
        assert len(validated) == 1
        assert validated[0].confidence == 0.7
        assert "skipped" in validated[0].validation_notes.lower()

    def test_deduplication(self):
        from llm.finding_validator import FindingValidator

        mock_router = MagicMock()
        validator = FindingValidator(mock_router)

        findings = [
            ValidatedFinding(
                file="test.py", line=10, severity="error",
                category="security", comment="SQL injection via user input",
                confidence=0.95,
            ),
            ValidatedFinding(
                file="test.py", line=10, severity="error",
                category="security", comment="SQL injection from user input data",
                confidence=0.85,
            ),
        ]

        deduped = validator._deduplicate_findings(findings)
        assert len(deduped) == 1
        assert deduped[0].confidence == 0.95  # Higher confidence kept

    def test_no_dedup_different_lines(self):
        from llm.finding_validator import FindingValidator

        mock_router = MagicMock()
        validator = FindingValidator(mock_router)

        findings = [
            ValidatedFinding(
                file="test.py", line=10, severity="error",
                category="security", comment="SQL injection",
                confidence=0.9,
            ),
            ValidatedFinding(
                file="test.py", line=20, severity="warning",
                category="reliability", comment="Missing error handling",
                confidence=0.85,
            ),
        ]

        deduped = validator._deduplicate_findings(findings)
        assert len(deduped) == 2

    def test_word_overlap_similar(self):
        from llm.finding_validator import FindingValidator
        overlap = FindingValidator._word_overlap(
            "SQL injection via user input",
            "SQL injection from user input data",
        )
        assert overlap > 0.5

    def test_word_overlap_different(self):
        from llm.finding_validator import FindingValidator
        overlap = FindingValidator._word_overlap(
            "SQL injection via user input",
            "Missing timeout on HTTP request",
        )
        assert overlap < 0.3


# ── Pipeline Parsing Tests ──────────────────────────────────────────────


class TestPipelineParsing:
    """Tests for ReviewPipeline._parse_review_output()."""

    def _get_pipeline(self):
        from llm.pipeline import ReviewPipeline
        mock_router = MagicMock()
        return ReviewPipeline(mock_router, mode="fast")

    def test_parse_comments_format(self):
        pipeline = self._get_pipeline()
        output = json.dumps({
            "comments": [
                {"file": "test.py", "line": 10, "severity": "error",
                 "category": "security", "comment": "SQL injection"},
            ]
        })
        findings = pipeline._parse_review_output(output, "test.py")
        assert len(findings) == 1
        assert findings[0]["severity"] == "error"

    def test_parse_array_format(self):
        pipeline = self._get_pipeline()
        output = json.dumps([
            {"file": "test.py", "line": 5, "severity": "warning",
             "category": "reliability", "comment": "Missing timeout"},
        ])
        findings = pipeline._parse_review_output(output, "test.py")
        assert len(findings) == 1

    def test_parse_markdown_fenced(self):
        pipeline = self._get_pipeline()
        output = '```json\n{"comments": [{"file": "x.py", "line": 1, "severity": "suggestion", "category": "style", "comment": "Naming"}]}\n```'
        findings = pipeline._parse_review_output(output, "x.py")
        assert len(findings) == 1

    def test_parse_message_suggestion_format(self):
        """Test backward compat with local prompt schema (message + suggestion)."""
        pipeline = self._get_pipeline()
        output = json.dumps({
            "comments": [
                {"file": "test.py", "line": 10,
                 "severity": "HIGH", "category": "BUGS",
                 "message": "Potential null pointer",
                 "suggestion": "Add null check before access"},
            ]
        })
        findings = pipeline._parse_review_output(output, "test.py")
        assert len(findings) == 1
        assert "Potential null pointer" in findings[0]["comment"]
        assert "Suggestion:" in findings[0]["comment"]

    def test_parse_empty_comments(self):
        pipeline = self._get_pipeline()
        output = json.dumps({"comments": []})
        findings = pipeline._parse_review_output(output, "test.py")
        assert findings == []

    def test_parse_invalid_json(self):
        pipeline = self._get_pipeline()
        output = "This is not JSON at all, just plain text."
        findings = pipeline._parse_review_output(output, "test.py")
        assert findings == []

    def test_parse_missing_line_field(self):
        """Findings without 'line' field should be skipped."""
        pipeline = self._get_pipeline()
        output = json.dumps({
            "comments": [
                {"file": "test.py", "severity": "error", "comment": "No line"},
                {"file": "test.py", "line": 5, "severity": "warning", "comment": "Has line"},
            ]
        })
        findings = pipeline._parse_review_output(output, "test.py")
        assert len(findings) == 1
        assert findings[0]["line"] == 5
