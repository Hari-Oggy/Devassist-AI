"""Pydantic data models for the analyzers package.

Defines the core data transfer objects shared by all tool runners:
``Severity``, ``LintFinding``, and ``ToolRunResult``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Classification of a finding's urgency level.

    Inherits from ``str`` so instances serialise naturally to JSON strings.
    """

    ERROR = "ERROR"
    WARNING = "WARNING"
    NOTE = "NOTE"


class LintFinding(BaseModel):
    """A single diagnostic finding emitted by a static-analysis tool.

    Attributes:
        file_path: Relative or absolute path to the source file that
            contains the finding.
        line: 1-indexed line number of the finding. Use ``0`` when the
            finding is not associated with a specific line (e.g. a
            package-level vulnerability).
        column: 1-indexed column number. ``None`` when unavailable.
        severity: Urgency classification — ``ERROR``, ``WARNING``, or
            ``NOTE``.
        rule_id: Tool-specific rule/check identifier, e.g. ``"E501"``,
            ``"B101"``, ``"CVE-2021-28363"``.
        message: Human-readable description of the finding.
        tool: Name of the tool that produced this finding.
        fix_suggestion: Optional actionable remediation text.
    """

    file_path: str
    line: int = 0
    column: Optional[int] = None
    severity: Severity = Severity.NOTE
    rule_id: str = ""
    message: str = ""
    tool: str = ""
    fix_suggestion: Optional[str] = None


class ToolRunResult(BaseModel):
    """Aggregated output from a single tool-runner execution.

    Attributes:
        tool: Name of the tool that was executed (mirrors
            ``BaseRunner.TOOL_NAME``).
        findings: List of :class:`LintFinding` objects produced by this
            run.  Empty when the tool produced no findings *or* when an
            error occurred.
        error: Non-``None`` when the tool could not complete normally.
            Contains a human-readable error description.
        exit_code: Raw process exit code, if the tool was invoked as a
            subprocess.  ``None`` when not applicable.
        duration_ms: Wall-clock milliseconds taken by the tool run,
            measured by the runner.  ``None`` when not recorded.
        raw_output: The unprocessed stdout captured from the tool, kept
            for debugging purposes.  May be ``None`` to conserve memory.
        timestamp: UTC timestamp at which this result was created.
    """

    tool: str
    findings: List[LintFinding] = Field(default_factory=list)
    error: Optional[str] = None
    exit_code: Optional[int] = None
    duration_ms: Optional[float] = None
    raw_output: Optional[str] = None
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def success(self) -> bool:
        """Return ``True`` when the run completed without a tool-level error.

        Returns:
            ``True`` if ``error`` is ``None``, ``False`` otherwise.
        """
        return self.error is None

    @property
    def finding_count(self) -> int:
        """Return the total number of findings produced.

        Returns:
            Integer count of :class:`LintFinding` entries.
        """
        return len(self.findings)


class SandboxResult(BaseModel):
    """Aggregated result from a full StaticAnalyzer run across all tools.

    Attributes:
        files_analyzed: List of file paths that were analyzed.
        tool_results: Per-tool ToolRunResult objects.
        all_findings: Flattened union of findings from every tool.
        total_duration_seconds: Wall-clock time for the full analysis run.
        errors: Non-fatal errors (e.g. tool not installed).
        container_id: Docker container ID if sandbox execution was used.
    """

    files_analyzed: List[str] = Field(default_factory=list)
    tool_results: List[ToolRunResult] = Field(default_factory=list)
    all_findings: List[LintFinding] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    errors: List[str] = Field(default_factory=list)
    container_id: str = ""

    def findings_by_file(self) -> dict[str, list[LintFinding]]:
        """Group findings by their file_path.

        Returns:
            Dict mapping file_path -> list of LintFinding.
        """
        result: dict[str, list[LintFinding]] = {}
        for f in self.all_findings:
            result.setdefault(f.file_path, []).append(f)
        return result

    def findings_by_severity(self) -> dict[str, list[LintFinding]]:
        """Group findings by their severity value.

        Returns:
            Dict mapping severity string -> list of LintFinding.
        """
        result: dict[str, list[LintFinding]] = {}
        for f in self.all_findings:
            key = f.severity.value if hasattr(f.severity, "value") else str(f.severity)
            result.setdefault(key, []).append(f)
        return result

    def error_count(self) -> int:
        """Return count of ERROR-severity findings."""
        return sum(1 for f in self.all_findings if f.severity == Severity.ERROR)

    def warning_count(self) -> int:
        """Return count of WARNING-severity findings."""
        return sum(1 for f in self.all_findings if f.severity == Severity.WARNING)

    def to_summary_string(self) -> str:
        """Return a human-readable summary line per tool.

        Returns:
            Multi-line string e.g. 'ruff: 3 findings (2 errors, 1 warning)'.
        """
        lines = []
        for tr in self.tool_results:
            if tr.error:
                lines.append(f"{tr.tool}: ERROR — {tr.error}")
            else:
                errors = sum(1 for f in tr.findings if f.severity == Severity.ERROR)
                warnings = sum(1 for f in tr.findings if f.severity == Severity.WARNING)
                lines.append(
                    f"{tr.tool}: {len(tr.findings)} findings "
                    f"({errors} errors, {warnings} warnings)"
                )
        return "\n".join(lines) if lines else "No tools ran."

