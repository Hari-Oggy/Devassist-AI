"""
Agentic Executor — runs AI-generated analysis scripts in Docker sandbox.

When the ensemble pipeline identifies a pattern that needs dynamic checking
(e.g., custom business logic validation, framework-specific rules), the
AgenticExecutor:
    1. Receives a Python analysis script from the LLM
    2. Validates the script (syntax check, banned imports, exec/eval detection)
    3. Writes it to a temp file
    4. Runs it in the Docker sandbox against the target code
    5. Returns structured LintFinding objects parsed from stdout
"""

from __future__ import annotations

import ast
import json
import os
import tempfile
import time
from typing import Optional

from analyzers.models import LintFinding, Severity, ToolRunResult
from core.logger import get_logger

logger = get_logger("analyzers.agentic_executor")

# Imports that are NEVER allowed in agentic scripts
_BANNED_IMPORTS: frozenset[str] = frozenset({
    "os", "subprocess", "shutil", "socket", "requests",
    "urllib", "httpx", "aiohttp", "paramiko", "ftplib",
    "pickle", "marshal", "shelve", "importlib",
    "ctypes", "cffi", "sys", "pty", "popen",
})

_MAX_SCRIPT_LINES = 200


class AgenticExecutor:
    """Executes AI-generated Python analysis scripts in a Docker sandbox.

    Scripts are validated for safety before execution. Findings are parsed
    from stdout (one JSON object per line).

    Example::

        executor = AgenticExecutor()
        is_valid, reason = executor.validate_script(script_code)
        if is_valid:
            result = executor.execute(script_code, "/path/to/repo")
    """

    TOOL_NAME = "agentic_script"

    def __init__(self, sandbox=None) -> None:
        """Initialise the executor.

        Args:
            sandbox: Optional pre-configured
                :class:`~analyzers.docker_sandbox.DockerSandbox`.
                If ``None``, scripts are run in a subprocess (dev mode only).
        """
        self.sandbox = sandbox

    # ── Public API ──────────────────────────────────────────────────────

    def execute(
        self,
        script: str,
        target_path: str,
        timeout: int = 30,
    ) -> ToolRunResult:
        """Validate and execute an AI-generated analysis script.

        Args:
            script: Python source code of the analysis script.
            target_path: Path to the code being analyzed.
            timeout: Maximum execution time in seconds.

        Returns:
            :class:`~analyzers.models.ToolRunResult` with any findings.
        """
        # 1. Validate
        is_valid, reason = self.validate_script(script)
        if not is_valid:
            logger.warning("Agentic script rejected: %s", reason)
            return ToolRunResult(
                tool=self.TOOL_NAME,
                error=f"Script validation failed: {reason}",
            )

        # 2. Write to temp file
        script_path = self._write_temp_script(script)
        start = time.time()

        try:
            # 3. Execute
            if self.sandbox and self.sandbox.is_available():
                exit_code, stdout, stderr = self.sandbox.run(
                    command=["python", f"/scripts/{os.path.basename(script_path)}", "/workspace"],
                    workdir=target_path,
                    extra_mounts=[f"{os.path.dirname(script_path)}:/scripts:ro"],
                )
            else:
                # Fallback: run locally (dev mode — not sandboxed)
                import subprocess
                result = subprocess.run(
                    ["python", script_path, target_path],
                    capture_output=True, text=True, timeout=timeout,
                )
                exit_code, stdout, stderr = result.returncode, result.stdout, result.stderr

            duration_ms = (time.time() - start) * 1000
            findings = self._parse_script_output(stdout)

            logger.info(
                "Agentic script: %d findings in %.1fms (exit=%d)",
                len(findings), duration_ms, exit_code,
            )

            return ToolRunResult(
                tool=self.TOOL_NAME,
                findings=findings,
                exit_code=exit_code,
                raw_output=stdout,
                duration_ms=duration_ms,
                error=stderr if exit_code != 0 else None,
            )

        except Exception as exc:
            logger.error("Agentic script execution error: %s", exc)
            return ToolRunResult(
                tool=self.TOOL_NAME,
                error=f"Execution error: {exc}",
            )
        finally:
            # Clean up temp file
            try:
                os.unlink(script_path)
            except OSError:
                pass

    def validate_script(self, script: str) -> tuple[bool, str]:
        """Validate an AI-generated script before execution.

        Checks:
            1. Valid Python syntax
            2. No banned imports (os, subprocess, socket, etc.)
            3. No ``exec()`` or ``eval()`` calls
            4. No ``open()`` calls
            5. Script length ≤ 200 lines

        Args:
            script: Python source code to validate.

        Returns:
            Tuple ``(is_valid, reason)``. ``reason`` is empty on success.
        """
        # 1. Length check
        lines = script.splitlines()
        if len(lines) > _MAX_SCRIPT_LINES:
            return False, (
                f"Script too long: {len(lines)} lines "
                f"(max {_MAX_SCRIPT_LINES})"
            )

        # 2. Syntax check
        try:
            tree = ast.parse(script)
        except SyntaxError as exc:
            return False, f"Syntax error: {exc}"

        # 3. Walk the AST for dangerous patterns
        for node in ast.walk(tree):
            # Banned imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    base = alias.name.split(".")[0]
                    if base in _BANNED_IMPORTS:
                        return False, f"Banned import: '{alias.name}'"

            if isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")[0]
                if module in _BANNED_IMPORTS:
                    return False, f"Banned import: 'from {node.module} import ...'"

            # exec() and eval() calls
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in ("exec", "eval"):
                    return False, f"Forbidden call: {func.id}()"
                if isinstance(func, ast.Name) and func.id == "open":
                    return False, "Forbidden call: open() — use /workspace path only"

            # __import__() calls
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "__import__":
                    return False, "Forbidden call: __import__()"

        return True, ""

    # ── Private helpers ─────────────────────────────────────────────────

    def _write_temp_script(self, script: str) -> str:
        """Write script to a temporary file and return its path.

        Args:
            script: Python source code to write.

        Returns:
            Absolute path to the temporary file.
        """
        fd, path = tempfile.mkstemp(suffix=".py", prefix="devassist_agent_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(script)
        except Exception:
            os.close(fd)
            raise
        return path

    def _parse_script_output(self, output: str) -> list[LintFinding]:
        """Parse findings from agentic script stdout.

        Expected format — one JSON object per line::

            {"file": "utils.py", "line": 10, "severity": "error", "message": "..."}

        Lines that cannot be parsed are silently skipped.

        Args:
            output: Captured stdout from the script.

        Returns:
            List of :class:`~analyzers.models.LintFinding` objects.
        """
        _sev_map = {
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
            "note": Severity.NOTE,
            "info": Severity.NOTE,
        }

        findings: list[LintFinding] = []
        for line in (output or "").splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
                sev_str = (obj.get("severity") or "note").lower()
                findings.append(
                    LintFinding(
                        tool=self.TOOL_NAME,
                        file_path=obj.get("file", ""),
                        line=int(obj.get("line", 0)),
                        severity=_sev_map.get(sev_str, Severity.NOTE),
                        rule_id=obj.get("rule_id", ""),
                        message=obj.get("message", ""),
                        fix_suggestion=obj.get("fix_suggestion"),
                    )
                )
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                logger.debug("agentic_executor: could not parse line: %s — %s", line[:80], exc)

        return findings
