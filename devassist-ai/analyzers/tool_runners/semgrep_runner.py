"""Semgrep — semantic pattern matching / SAST scanner."""

from __future__ import annotations

import json
import time
from typing import Optional

from analyzers.models import LintFinding, Severity, ToolRunResult
from analyzers.tool_runners.base_runner import BaseRunner
from core.logger import get_logger

logger = get_logger("analyzers.tool_runners.semgrep")

_SEV_MAP: dict[str, Severity] = {
    "ERROR": Severity.ERROR,
    "WARNING": Severity.WARNING,
    "INFO": Severity.NOTE,
    "INVENTORY": Severity.NOTE,
    "EXPERIMENT": Severity.NOTE,
}


class SemgrepRunner(BaseRunner):
    """Tool runner for Semgrep — semantic SAST scanner.

    Invokes ``semgrep --config auto --json <target>`` and parses the
    JSON output. Returns an empty result (not an error) when semgrep
    is not installed, so the pipeline degrades gracefully.
    """

    TOOL_NAME = "semgrep"

    def is_available(self) -> bool:
        return self._which("semgrep")

    def run(
        self,
        target_path: str,
        file_paths: Optional[list[str]] = None,
    ) -> ToolRunResult:
        if not self.is_available():
            return ToolRunResult(
                tool=self.TOOL_NAME,
                error="semgrep not installed — install with: pip install semgrep",
            )

        targets = file_paths if file_paths else [target_path]
        cmd = ["semgrep", "--config", "auto", "--json"] + targets

        start = time.time()
        exit_code, stdout, stderr = self._run_command(cmd, timeout=180)
        duration_ms = (time.time() - start) * 1000

        if exit_code == -2:
            return ToolRunResult(tool=self.TOOL_NAME, error=stderr)

        findings = self.parse_output(stdout, target_path)
        logger.info("semgrep: %d findings in %.1fms", len(findings), duration_ms)

        return ToolRunResult(
            tool=self.TOOL_NAME,
            findings=findings,
            exit_code=exit_code,
            raw_output=stdout,
            duration_ms=duration_ms,
            error=stderr if exit_code not in (0, 1) else None,
        )

    def parse_output(self, raw_output: str, target_path: str) -> list[LintFinding]:
        """Parse Semgrep JSON output.

        Semgrep JSON format::

            {
                "results": [
                    {
                        "path": "auth.py",
                        "start": {"line": 10},
                        "check_id": "python.lang.security.assert-used",
                        "extra": {
                            "message": "Assert found",
                            "severity": "WARNING"
                        }
                    }
                ]
            }
        """
        if not raw_output or not raw_output.strip():
            return []

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError:
            logger.debug("semgrep: could not parse JSON output")
            return []

        results = data.get("results", [])
        if not isinstance(results, list):
            return []

        findings = []
        for item in results:
            try:
                extra = item.get("extra", {})
                sev_str = (extra.get("severity") or "WARNING").upper()
                check_id = item.get("check_id", "")
                findings.append(
                    LintFinding(
                        tool=self.TOOL_NAME,
                        file_path=item.get("path", ""),
                        line=item.get("start", {}).get("line", 0),
                        severity=_SEV_MAP.get(sev_str, Severity.WARNING),
                        rule_id=check_id,
                        message=extra.get("message", ""),
                        fix_suggestion=extra.get("fix", None),
                    )
                )
            except Exception as exc:
                logger.debug("semgrep: skipping malformed finding: %s", exc)

        return findings
