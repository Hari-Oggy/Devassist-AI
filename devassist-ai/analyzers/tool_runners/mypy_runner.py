"""Mypy — Python static type checker. Supports both plain text and JSON output."""

from __future__ import annotations

import json
import re
import time
from typing import Optional

from analyzers.models import LintFinding, Severity, ToolRunResult
from analyzers.tool_runners.base_runner import BaseRunner
from core.logger import get_logger

logger = get_logger("analyzers.tool_runners.mypy")

# Regex for plain-text mypy output: path:line: severity: message
_PLAIN_PATTERN = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?P<severity>error|warning|note):\s*(?P<message>.+)$"
)

_SEV_MAP: dict[str, Severity] = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "note": Severity.NOTE,
}


class MypyRunner(BaseRunner):
    """Tool runner for Mypy — Python static type checker.

    Attempts JSON output first (``--output=json``, mypy >= 0.900).
    Falls back to plain-text line-by-line parsing for older versions.
    """

    TOOL_NAME = "mypy"

    def is_available(self) -> bool:
        return self._which("mypy")

    def run(
        self,
        target_path: str,
        file_paths: Optional[list[str]] = None,
    ) -> ToolRunResult:
        if not self.is_available():
            return ToolRunResult(
                tool=self.TOOL_NAME,
                error="mypy not found — install with: pip install mypy",
            )

        targets = file_paths if file_paths else [target_path]

        # Try JSON output mode first (mypy >= 0.900)
        cmd_json = ["mypy", "--no-error-summary", "--output=json"] + targets
        start = time.time()
        exit_code, stdout, stderr = self._run_command(cmd_json, timeout=120)
        duration_ms = (time.time() - start) * 1000

        if exit_code == -2:
            return ToolRunResult(tool=self.TOOL_NAME, error=stderr)

        findings = self.parse_output(stdout or stderr, target_path)
        if not findings and (stdout or stderr):
            # JSON mode may not be supported — retry with plain text
            cmd_plain = ["mypy", "--no-error-summary"] + targets
            _, stdout2, stderr2 = self._run_command(cmd_plain, timeout=120)
            findings = self.parse_output(stdout2 or stderr2, target_path)

        logger.info("mypy: %d findings in %.1fms", len(findings), duration_ms)

        return ToolRunResult(
            tool=self.TOOL_NAME,
            findings=findings,
            exit_code=exit_code,
            raw_output=stdout,
            duration_ms=duration_ms,
            error=None,
        )

    def parse_output(self, raw_output: str, target_path: str) -> list[LintFinding]:
        """Parse mypy output — tries JSON then falls back to plain text.

        JSON format (one object per line)::

            {"file": "utils.py", "line": 10, "severity": "error", "message": "..."}

        Plain text format::

            utils.py:10: error: Incompatible types ...
        """
        if not raw_output or not raw_output.strip():
            return []

        findings: list[LintFinding] = []

        for line in raw_output.splitlines():
            line = line.strip()
            if not line:
                continue

            # Try JSON object per line
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                    sev_str = (obj.get("severity") or "note").lower()
                    findings.append(
                        LintFinding(
                            tool=self.TOOL_NAME,
                            file_path=obj.get("file", ""),
                            line=obj.get("line", 0),
                            column=obj.get("column"),
                            severity=_SEV_MAP.get(sev_str, Severity.NOTE),
                            rule_id=obj.get("code", ""),
                            message=obj.get("message", ""),
                        )
                    )
                    continue
                except json.JSONDecodeError:
                    pass

            # Fall back to plain-text regex
            m = _PLAIN_PATTERN.match(line)
            if m:
                sev_str = m.group("severity").lower()
                findings.append(
                    LintFinding(
                        tool=self.TOOL_NAME,
                        file_path=m.group("file"),
                        line=int(m.group("line")),
                        severity=_SEV_MAP.get(sev_str, Severity.NOTE),
                        message=m.group("message"),
                    )
                )

        return findings
