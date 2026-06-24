"""Trivy — container and filesystem vulnerability scanner (multi-language)."""

from __future__ import annotations

import json
import time
from typing import Optional

from analyzers.models import LintFinding, Severity, ToolRunResult
from analyzers.tool_runners.base_runner import BaseRunner
from core.logger import get_logger

logger = get_logger("analyzers.tool_runners.trivy")

_SEV_MAP: dict[str, Severity] = {
    "CRITICAL": Severity.ERROR,
    "HIGH": Severity.ERROR,
    "MEDIUM": Severity.WARNING,
    "LOW": Severity.NOTE,
    "UNKNOWN": Severity.NOTE,
}


class TrivyRunner(BaseRunner):
    """Tool runner for Trivy — multi-language CVE/SBOM scanner.

    Invokes ``trivy fs --format json --quiet <target>`` and parses the
    Results array into :class:`~analyzers.models.LintFinding` objects.
    Covers Python, Go, Node.js, Rust, Java, and container image scanning.
    """

    TOOL_NAME = "trivy"

    def is_available(self) -> bool:
        return self._which("trivy")

    def run(
        self,
        target_path: str,
        file_paths: Optional[list[str]] = None,
    ) -> ToolRunResult:
        if not self.is_available():
            return ToolRunResult(
                tool=self.TOOL_NAME,
                error="trivy not found — install from https://github.com/aquasecurity/trivy",
            )

        cmd = ["trivy", "fs", "--format", "json", "--quiet", target_path]

        start = time.time()
        exit_code, stdout, stderr = self._run_command(cmd, timeout=180)
        duration_ms = (time.time() - start) * 1000

        if exit_code == -2:
            return ToolRunResult(tool=self.TOOL_NAME, error=stderr)

        findings = self.parse_output(stdout, target_path)
        logger.info("trivy: %d vulnerabilities in %.1fms", len(findings), duration_ms)

        return ToolRunResult(
            tool=self.TOOL_NAME,
            findings=findings,
            exit_code=exit_code,
            raw_output=stdout,
            duration_ms=duration_ms,
            error=stderr if exit_code not in (0, 1) else None,
        )

    def parse_output(self, raw_output: str, target_path: str) -> list[LintFinding]:
        """Parse Trivy filesystem scan JSON output.

        Trivy JSON format::

            {
                "Results": [
                    {
                        "Target": "requirements.txt",
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2022-99999",
                                "PkgName": "pillow",
                                "InstalledVersion": "8.0.0",
                                "FixedVersion": "9.0.0",
                                "Severity": "CRITICAL",
                                "Description": "..."
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
            logger.debug("trivy: could not parse JSON output")
            return []

        results = data.get("Results", [])
        if not isinstance(results, list):
            return []

        findings = []
        for result_block in results:
            target_file = result_block.get("Target", "unknown")
            vulns = result_block.get("Vulnerabilities") or []
            for vuln in vulns:
                try:
                    sev_str = (vuln.get("Severity") or "UNKNOWN").upper()
                    pkg = vuln.get("PkgName", "?")
                    installed = vuln.get("InstalledVersion", "?")
                    fixed = vuln.get("FixedVersion", "")
                    cve_id = vuln.get("VulnerabilityID", "")
                    desc = vuln.get("Description", "")
                    findings.append(
                        LintFinding(
                            tool=self.TOOL_NAME,
                            file_path=target_file,
                            line=0,
                            severity=_SEV_MAP.get(sev_str, Severity.NOTE),
                            rule_id=cve_id,
                            message=f"{pkg}=={installed} — {desc[:200]}",
                            fix_suggestion=f"Upgrade to {fixed}" if fixed else None,
                        )
                    )
                except Exception as exc:
                    logger.debug("trivy: skipping malformed vuln: %s", exc)

        return findings
