"""
Static Analyzer — parallel multi-tool orchestration for DevAssist-AI.

Runs all applicable static analysis tool runners concurrently using
ThreadPoolExecutor and aggregates findings into a unified SandboxResult.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from analyzers.models import LintFinding, SandboxResult, ToolRunResult
from analyzers.tool_runners import ALL_RUNNERS, PYTHON_RUNNERS
from analyzers.tool_runners.base_runner import BaseRunner
from core.logger import get_logger

logger = get_logger("analyzers.static_analyzer")

# Map language label → applicable runner classes
_LANGUAGE_RUNNERS: dict[str, list[type[BaseRunner]]] = {
    "python": PYTHON_RUNNERS,
    "javascript": ALL_RUNNERS,
    "typescript": ALL_RUNNERS,
    "java": ALL_RUNNERS,
    "rust": ALL_RUNNERS,
    "go": ALL_RUNNERS,
    "multi": ALL_RUNNERS,
}


class StaticAnalyzer:
    """Parallel orchestrator for all static analysis tool runners.

    Selects applicable runners based on the target language, checks which
    are installed, and runs them concurrently with a thread pool.

    Example::

        analyzer = StaticAnalyzer(max_workers=4)
        result = analyzer.analyze("/path/to/repo", language="python")
        print(result.to_summary_string())
    """

    def __init__(
        self,
        use_sandbox: bool = False,
        sandbox=None,
        max_workers: int = 4,
    ) -> None:
        """Initialise the analyzer.

        Args:
            use_sandbox: If True, run tools inside a Docker sandbox.
            sandbox: Optional pre-configured :class:`~analyzers.docker_sandbox.DockerSandbox`.
            max_workers: Maximum number of tool runners to run concurrently.
        """
        self.use_sandbox = use_sandbox
        self.sandbox = sandbox
        self.max_workers = max_workers

    # ── Public API ──────────────────────────────────────────────────────

    def analyze(
        self,
        target_path: str,
        file_paths: Optional[list[str]] = None,
        tools: Optional[list[str]] = None,
        language: str = "python",
    ) -> SandboxResult:
        """Run all applicable tool runners in parallel.

        Args:
            target_path: Root directory or file to analyse.
            file_paths: Optional subset of files to check within target_path.
            tools: Optional list of TOOL_NAME strings to restrict which
                runners execute.  ``None`` means run all available.
            language: Target language/ecosystem — controls runner selection.

        Returns:
            :class:`~analyzers.models.SandboxResult` with aggregated findings.
        """
        start = time.time()
        runner_instances = self._select_runners(language, tools)

        logger.info(
            "StaticAnalyzer: running %d runners on %s (workers=%d)",
            len(runner_instances), target_path, self.max_workers,
        )

        tool_results: list[ToolRunResult] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._run_single, runner, target_path, file_paths): runner
                for runner in runner_instances
            }
            for future in as_completed(futures):
                runner = futures[future]
                try:
                    result = future.result()
                    tool_results.append(result)
                    logger.info(
                        "  %s: %d findings (error=%s)",
                        result.tool, len(result.findings), result.error,
                    )
                except Exception as exc:
                    logger.error("Unhandled exception from %s: %s", runner.TOOL_NAME, exc)
                    tool_results.append(
                        ToolRunResult(tool=runner.TOOL_NAME, error=str(exc))
                    )

        all_findings: list[LintFinding] = []
        errors: list[str] = []
        for tr in tool_results:
            all_findings.extend(tr.findings)
            if tr.error:
                errors.append(f"{tr.tool}: {tr.error}")

        total_duration = time.time() - start
        logger.info(
            "StaticAnalyzer complete: %d total findings in %.2fs",
            len(all_findings), total_duration,
        )

        return SandboxResult(
            files_analyzed=file_paths or [target_path],
            tool_results=tool_results,
            all_findings=all_findings,
            total_duration_seconds=total_duration,
            errors=errors,
        )

    # ── Private helpers ─────────────────────────────────────────────────

    def _select_runners(
        self,
        language: str,
        tools: Optional[list[str]],
    ) -> list[BaseRunner]:
        """Instantiate and return the applicable runner objects.

        Args:
            language: Target ecosystem key.
            tools: Optional allowlist of TOOL_NAME strings.

        Returns:
            List of instantiated :class:`~analyzers.tool_runners.base_runner.BaseRunner`.
        """
        runner_classes = _LANGUAGE_RUNNERS.get(language.lower(), PYTHON_RUNNERS)

        # Apply optional tools filter
        if tools:
            runner_classes = [r for r in runner_classes if r.TOOL_NAME in tools]

        instances = [cls() for cls in runner_classes]

        # Filter to only installed tools (log skipped ones)
        available = []
        for runner in instances:
            if runner.is_available():
                available.append(runner)
            else:
                logger.debug("%s not available — skipping", runner.TOOL_NAME)

        return available

    def _run_single(
        self,
        runner: BaseRunner,
        target_path: str,
        file_paths: Optional[list[str]],
    ) -> ToolRunResult:
        """Safely execute a single tool runner.

        Catches all exceptions so one failing tool never aborts the run.

        Args:
            runner: Instantiated runner to execute.
            target_path: Path to the code being analysed.
            file_paths: Optional file subset to pass to the runner.

        Returns:
            :class:`~analyzers.models.ToolRunResult` (may have error set).
        """
        try:
            logger.debug("Starting %s ...", runner.TOOL_NAME)
            result = runner.run(target_path, file_paths)
            return result
        except Exception as exc:
            logger.error("%s raised an unexpected error: %s", runner.TOOL_NAME, exc)
            return ToolRunResult(
                tool=runner.TOOL_NAME,
                error=f"{runner.TOOL_NAME} crashed: {exc}",
            )
