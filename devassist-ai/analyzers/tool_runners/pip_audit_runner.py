"""pip-audit — Python dependency vulnerability scanner (CVE/PyPA advisories)."""

from __future__ import annotations

import json
import time
from typing import Optional

from analyzers.models import LintFinding, Severity, ToolRunResult
from analyzers.tool_runners.base_runner import BaseRunner
from core.logger import get_logger

logger = get_logger("analyzers.tool_runners.pip_audit")


class PipAuditRunner(BaseRunner):
    """Tool runner for pip-audit — Python dependency CVE scanner.

    Invokes ``pip-audit --format json`` and maps each vulnerability to a
    :class:`~analyzers.models.LintFinding` with ``severity=ERROR``.

    If a ``requirements.txt`` exists in *target_path*, uses
    ``-r requirements.txt`` for reproducible offline analysis.
    """

    TOOL_NAME = "pip_audit"

    def is_available(self) -> bool:
        return self._which("pip-audit")

    def run(
        self,
        target_path: str,
        file_paths: Optional[list[str]] = None,
    ) -> ToolRunResult:
        if not self.is_available():
            return ToolRunResult(
                tool=self.TOOL_NAME,
                error="pip-audit not found — install with: pip install pip-audit",
            )

        import os
        req_file = os.path.join(target_path, "requirements.txt")
        if os.path.isfile(req_file):
            cmd = ["pip-audit", "-r", req_file, "--format", "json"]
        else:
            cmd = ["pip-audit", "--format", "json"]

        start = time.time()
        exit_code, stdout, stderr = self._run_command(cmd, timeout=120, cwd=target_path)
        duration_ms = (time.time() - start) * 1000

        if exit_code == -2:
            return ToolRunResult(tool=self.TOOL_NAME, error=stderr)

        findings = self.parse_output(stdout, target_path)
        logger.info("pip-audit: %d vulnerabilities in %.1fms", len(findings), duration_ms)

        return ToolRunResult(
            tool=self.TOOL_NAME,
            findings=findings,
            exit_code=exit_code,
            raw_output=stdout,
            duration_ms=duration_ms,
            error=stderr if exit_code not in (0, 1) else None,
        )

    def parse_output(self, raw_output: str, target_path: str) -> list[LintFinding]:
        """Parse pip-audit JSON output.

        pip-audit JSON format::

            {
                "dependencies": [
                    {
                        "name": "requests",
                        "version": "2.25.0",
                        "vulns": [
                            {
                                "id": "CVE-2021-28363",
                                "fix_versions": ["2.26.0"],
                                "description": "..."
                            }
                        ]
                    }
                ]
            }
        """
        if not raw_output or not raw_output.strip():
            return []

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError:
            logger.debug("pip-audit: could not parse JSON output")
            return []

        dependencies = data.get("dependencies", [])
        if not isinstance(dependencies, list):
            return []

        findings = []
        for dep in dependencies:
            name = dep.get("name", "unknown")
            version = dep.get("version", "?")
            for vuln in dep.get("vulns", []):
                try:
                    cve_id = vuln.get("id", "UNKNOWN-CVE")
                    fix_versions = vuln.get("fix_versions", [])
                    description = vuln.get("description", "")
                    findings.append(
                        LintFinding(
                            tool=self.TOOL_NAME,
                            file_path="requirements.txt",
                            line=0,
                            severity=Severity.ERROR,
                            rule_id=cve_id,
                            message=(
                                f"{name}=={version} has known vulnerability: "
                                f"{description[:200]}"
                            ),
                            fix_suggestion=(
                                f"Upgrade to {', '.join(fix_versions)}"
                                if fix_versions else "No fix version available"
                            ),
                        )
                    )
                except Exception as exc:
                    logger.debug("pip-audit: skipping malformed vuln: %s", exc)

        return findings
