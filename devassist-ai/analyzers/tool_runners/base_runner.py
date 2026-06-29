"""
Abstract base class for all static analysis tool runners.

Each concrete runner wraps one external CLI tool and exposes a uniform
interface for the StaticAnalyzer to call without tool-specific knowledge.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from typing import Optional

from analyzers.models import LintFinding, ToolRunResult
from core.logger import get_logger

logger = get_logger("analyzers.tool_runners.base")


class BaseRunner(ABC):
    """Abstract base for all static analysis tool runners.

    Subclasses must implement :meth:`is_available`, :meth:`run`, and
    :meth:`parse_output`. They may also use the protected helpers
    :meth:`_run_command` and :meth:`_which`.

    Class Attributes:
        TOOL_NAME: Short identifier for this tool, e.g. ``'ruff'``.
    """

    TOOL_NAME: str = ""

    # ── Abstract interface ──────────────────────────────────────────────

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this tool is installed and executable."""

    @abstractmethod
    def run(
        self,
        target_path: str,
        file_paths: Optional[list[str]] = None,
    ) -> ToolRunResult:
        """Run the tool against target_path.

        Args:
            target_path: Root directory or single file to analyse.
            file_paths: Optional subset of specific files to check.

        Returns:
            :class:`~analyzers.models.ToolRunResult` with parsed findings.
        """

    @abstractmethod
    def parse_output(self, raw_output: str, target_path: str) -> list[LintFinding]:
        """Parse raw tool stdout into a list of LintFinding objects.

        Args:
            raw_output: The captured stdout from the tool process.
            target_path: Repository root (used to normalise file paths).

        Returns:
            List of :class:`~analyzers.models.LintFinding`.
        """

    # ── Shared protected helpers ────────────────────────────────────────

    def __init__(self):
        self.sandbox = None

    def _run_command(
        self,
        cmd: list[str],
        timeout: int = 60,
        cwd: Optional[str] = None,
    ) -> tuple[int, str, str]:
        """Run a subprocess command and return (exit_code, stdout, stderr).

        Handles ``FileNotFoundError`` (tool not installed) and
        ``TimeoutExpired`` without raising.

        Args:
            cmd: Command list to execute.
            timeout: Max seconds to wait before aborting.
            cwd: Optional working directory for the subprocess.

        Returns:
            Tuple ``(exit_code, stdout, stderr)``.
        """
        # --- Secure execution path using DockerSandbox ---
        if self.sandbox:
            res = self.sandbox.run_command(
                command=cmd,
                repo_path=cwd if cwd else ".",
                timeout=timeout,
            )
            return res.exit_code, res.stdout, res.stderr
        # -----------------------------------------------

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.warning("%s timed out after %ds", self.TOOL_NAME, timeout)
            return -1, "", f"{self.TOOL_NAME} timed out after {timeout}s"
        except FileNotFoundError:
            return -2, "", f"{self.TOOL_NAME} not found — is it installed?"
        except Exception as exc:
            logger.error("Unexpected error running %s: %s", self.TOOL_NAME, exc)
            return -3, "", str(exc)

    def _which(self, tool: str) -> bool:
        """Return True if *tool* binary is present on PATH.

        Args:
            tool: Binary name to search for, e.g. ``'ruff'``.

        Returns:
            ``True`` if found, ``False`` otherwise.
        """
        return shutil.which(tool) is not None
