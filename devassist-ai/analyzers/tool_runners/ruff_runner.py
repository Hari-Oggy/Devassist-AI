"""Ruff — fast Python linter. Produces JSON output."""

from __future__ import annotations

import json
import time
from typing import Optional

from analyzers.models import LintFinding, Severity, ToolRunResult
from analyzers.tool_runners.base_runner import BaseRunner
from core.logger import get_logger

logger = get_logger("analyzers.tool_runners.ruff")

# Ruff code prefix → Severity
_PREFIX_SEVERITY: dict[str, Severity] = {
    "E": Severity.ERROR,
    "F": Severity.ERROR,
    "W": Severity.WARNING,
    "C": Severity.WARNING,
    "N": Severity.NOTE,
    "D": Severity.NOTE,
    "I": Severity.NOTE,
    "UP": Severity.NOTE,
    "B": Severity.WARNING,
    "S": Severity.ERROR,   # flake8-bandit security rules
    "T": Severity.WARNING,
    "A": Severity.WARNING,
    "ANN": Severity.NOTE,
    "RUF": Severity.WARNING,
}


def _map_severity(code: str) -> Severity:
    """Map a ruff rule code to Severity."""
    for prefix, sev in _PREFIX_SEVERITY.items():
        if code.startswith(prefix):
            return sev
    return Severity.NOTE


class RuffRunner(BaseRunner):
    """Tool runner for Ruff — the fast Python linter/formatter.

    Invokes ``ruff check --output-format json <target>`` and parses
    the JSON array output into :class:`~analyzers.models.LintFinding` objects.
    """

    TOOL_NAME = "ruff"

    def is_available(self) -> bool:
        return self._which("ruff")

    def run(
        self,
        target_path: str,
        file_paths: Optional[list[str]] = None,
    ) -> ToolRunResult:
        if not self.is_available():
            return ToolRunResult(
                tool=self.TOOL_NAME,
                error="ruff not found — install with: pip install ruff",
            )

        targets = file_paths if file_paths else [target_path]
        cmd = ["ruff", "check", "--output-format", "json"] + targets

        start = time.time()
        exit_code, stdout, stderr = self._run_command(cmd, timeout=60)
        duration_ms = (time.time() - start) * 1000

        if exit_code == -2:
            return ToolRunResult(tool=self.TOOL_NAME, error=stderr)

        findings = self.parse_output(stdout, target_path)
        logger.info("ruff: %d findings in %.1fms", len(findings), duration_ms)

        return ToolRunResult(
            tool=self.TOOL_NAME,
            findings=findings,
            exit_code=exit_code,
            raw_output=stdout,
            duration_ms=duration_ms,
            error=stderr if exit_code not in (0, 1) else None,
        )

    def parse_output(self, raw_output: str, target_path: str) -> list[LintFinding]:
        """Parse ruff JSON array output.

        Ruff exits with code 1 when findings exist, which is still valid output.
        """
        if not raw_output or not raw_output.strip():
            return []

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError:
            logger.debug("ruff: could not parse JSON output")
            return []

        if not isinstance(data, list):
            return []

        findings = []
        for item in data:
            try:
                code = item.get("code") or item.get("rule_id") or ""
                location = item.get("location") or item.get("start") or {}
                findings.append(
                    LintFinding(
                        tool=self.TOOL_NAME,
                        file_path=item.get("filename", ""),
                        line=location.get("row", location.get("line", 0)),
                        column=location.get("column", location.get("col")),
                        severity=_map_severity(code),
                        rule_id=code,
                        message=item.get("message", ""),
                        fix_suggestion=(
                            item.get("fix", {}).get("message", "")
                            if isinstance(item.get("fix"), dict)
                            else None
                        ),
                    )
                )
            except Exception as exc:
                logger.debug("ruff: skipping malformed finding: %s", exc)

        return findings
