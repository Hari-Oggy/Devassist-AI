"""Bandit — Python security scanner. Produces JSON output."""

from __future__ import annotations

import json
import time
from typing import Optional

from analyzers.models import LintFinding, Severity, ToolRunResult
from analyzers.tool_runners.base_runner import BaseRunner
from core.logger import get_logger

logger = get_logger("analyzers.tool_runners.bandit")

_SEVERITY_MAP: dict[str, Severity] = {
    "HIGH": Severity.ERROR,
    "MEDIUM": Severity.WARNING,
    "LOW": Severity.NOTE,
    "UNDEFINED": Severity.NOTE,
}


class BanditRunner(BaseRunner):
    """Tool runner for Bandit — Python security issue scanner.

    Invokes ``bandit -r -f json <target>`` and parses the JSON output
    into :class:`~analyzers.models.LintFinding` objects.
    """

    TOOL_NAME = "bandit"

    def is_available(self) -> bool:
        return self._which("bandit")

    def run(
        self,
        target_path: str,
        file_paths: Optional[list[str]] = None,
    ) -> ToolRunResult:
        if not self.is_available():
            return ToolRunResult(
                tool=self.TOOL_NAME,
                error="bandit not found — install with: pip install bandit",
            )

        target = file_paths[0] if file_paths and len(file_paths) == 1 else target_path
        cmd = ["bandit", "-r", "-f", "json", target]

        start = time.time()
        exit_code, stdout, stderr = self._run_command(cmd, timeout=60)
        duration_ms = (time.time() - start) * 1000

        if exit_code == -2:
            return ToolRunResult(tool=self.TOOL_NAME, error=stderr)

        findings = self.parse_output(stdout, target_path)
        logger.info("bandit: %d findings in %.1fms", len(findings), duration_ms)

        return ToolRunResult(
            tool=self.TOOL_NAME,
            findings=findings,
            exit_code=exit_code,
            raw_output=stdout,
            duration_ms=duration_ms,
            # bandit exits 1 when issues found — that's normal
            error=stderr if exit_code not in (0, 1) else None,
        )

    def parse_output(self, raw_output: str, target_path: str) -> list[LintFinding]:
        """Parse Bandit JSON output.

        Bandit JSON format::

            {
                "results": [
                    {
                        "filename": "auth.py",
                        "line_number": 42,
                        "test_id": "B101",
                        "issue_text": "...",
                        "issue_severity": "HIGH",
                        "issue_confidence": "HIGH"
                    }
                ]
            }
        """
        if not raw_output or not raw_output.strip():
            return []

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError:
            logger.debug("bandit: could not parse JSON output")
            return []

        results = data.get("results", [])
        if not isinstance(results, list):
            return []

        findings = []
        for item in results:
            try:
                sev_str = (item.get("issue_severity") or "LOW").upper()
                findings.append(
                    LintFinding(
                        tool=self.TOOL_NAME,
                        file_path=item.get("filename", ""),
                        line=item.get("line_number", 0),
                        severity=_SEVERITY_MAP.get(sev_str, Severity.NOTE),
                        rule_id=item.get("test_id", ""),
                        message=item.get("issue_text", ""),
                        fix_suggestion=f"Confidence: {item.get('issue_confidence', '?')}",
                    )
                )
            except Exception as exc:
                logger.debug("bandit: skipping malformed finding: %s", exc)

        return findings
