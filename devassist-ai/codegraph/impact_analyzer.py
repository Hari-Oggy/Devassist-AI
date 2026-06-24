"""Impact analyser for CodeGraph.

Given a :class:`~codegraph.graph_builder.CodeGraph` and a list of files
changed by a pull request, :class:`ImpactAnalyzer` computes the blast radius
of every changed symbol through BFS traversal of the caller graph and
produces a structured :class:`~codegraph.models.ImpactReport`.

Typical usage::

    from codegraph.graph_builder import CodeGraphBuilder
    from codegraph.impact_analyzer import ImpactAnalyzer

    graph    = CodeGraphBuilder("/repo").build()
    analyzer = ImpactAnalyzer(graph)
    report   = analyzer.analyze(changed_files=["src/utils.py"], pr_number=42)
"""

from __future__ import annotations

from collections import deque

from core.logger import get_logger
from codegraph.graph_builder import CodeGraph
from codegraph.models import ChangeImpact, ImpactReport, Symbol

logger = get_logger("codegraph.impact_analyzer")

# Blast-radius thresholds (inclusive lower bound → label)
_BLAST_THRESHOLDS: list[tuple[int, str]] = [
    (21, "CRITICAL"),
    (6,  "HIGH"),
    (1,  "MEDIUM"),
    (0,  "LOW"),
]

# Severity ordering used to promote the PR-level blast radius to the worst-case
_SEVERITY_ORDER: dict[str, int] = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2,
    "CRITICAL": 3,
}


class ImpactAnalyzer:
    """Computes the blast radius of changed files within a :class:`CodeGraph`.

    The analyser walks the *caller* graph (bottom-up) using BFS up to
    ``max_depth`` hops to discover transitive callers.  It classifies each
    changed symbol with a qualitative blast-radius label and detects
    potentially breaking public-API changes.

    Args:
        graph: A fully-built :class:`~codegraph.graph_builder.CodeGraph`.

    Example::

        analyzer = ImpactAnalyzer(graph)
        report   = analyzer.analyze(["api/routes.py", "core/utils.py"], pr_number=7)
    """

    def __init__(self, graph: CodeGraph) -> None:
        self.graph: CodeGraph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        changed_files: list[str],
        pr_number: int = 0,
    ) -> ImpactReport:
        """Compute the full impact of changes across a list of files.

        Algorithm per changed file:

        1. Collect all symbols defined in that file via
           :meth:`~codegraph.graph_builder.CodeGraph.get_symbols_in_file`.
        2. For each symbol, find *direct* callers with
           :meth:`~codegraph.graph_builder.CodeGraph.get_callers`.
        3. Walk the caller chain transitively up to depth 3 via
           :meth:`_get_transitive_callers`.
        4. Compute a :class:`~codegraph.models.ChangeImpact` record.
        5. Detect potentially *breaking* public-API changes.

        Args:
            changed_files: Relative file paths (from repository root) of
                files modified in the pull request.
            pr_number: GitHub pull-request number attached to the report.

        Returns:
            A populated :class:`~codegraph.models.ImpactReport`.
        """
        report = ImpactReport(pr_number=pr_number)
        pr_blast_severity = 0  # tracks worst-case severity index across symbols

        logger.info(
            "Starting impact analysis",
            extra={"pr_number": pr_number, "changed_files": len(changed_files)},
        )

        for file_path in changed_files:
            symbols_in_file = self.graph.get_symbols_in_file(file_path)

            if not symbols_in_file:
                logger.info(
                    "No symbols found in changed file — skipping",
                    extra={"file": file_path},
                )
                continue

            for sym in symbols_in_file:
                try:
                    impact = self._analyze_symbol(sym)
                except Exception as exc:  # noqa: BLE001
                    msg = f"Error analysing {sym.qualified_name}: {exc}"
                    logger.warning(msg)
                    report.analysis_errors.append(msg)
                    continue

                report.changed_symbols[sym.qualified_name] = impact

                # Accumulate affected files at PR level
                for fp in impact.affected_files:
                    if fp not in report.affected_files:
                        report.affected_files.append(fp)

                # Track high-risk symbols
                if impact.blast_radius in ("HIGH", "CRITICAL"):
                    report.high_risk_changes.append(impact)

                # Detect breaking changes for exported symbols with callers
                if sym.is_exported and impact.direct_callers:
                    report.breaking_changes.append(
                        {
                            "type": "function_change",
                            "function": sym.qualified_name,
                            "description": (
                                f"Public symbol '{sym.qualified_name}' "
                                f"({sym.kind.value}) was modified and has "
                                f"{len(impact.direct_callers)} direct caller(s). "
                                "Any signature changes may break callers."
                            ),
                        }
                    )

                # Promote PR-level blast radius to worst case
                sym_severity = _SEVERITY_ORDER.get(impact.blast_radius, 0)
                if sym_severity > pr_blast_severity:
                    pr_blast_severity = sym_severity
                    report.blast_radius = impact.blast_radius

        logger.info(
            "Impact analysis complete",
            extra={
                "pr_number": pr_number,
                "changed_symbols": len(report.changed_symbols),
                "breaking_changes": len(report.breaking_changes),
                "high_risk": len(report.high_risk_changes),
                "blast_radius": report.blast_radius,
            },
        )

        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _analyze_symbol(self, sym: Symbol) -> ChangeImpact:
        """Produce a :class:`~codegraph.models.ChangeImpact` for one symbol.

        Args:
            sym: The changed :class:`~codegraph.models.Symbol`.

        Returns:
            A fully-populated :class:`~codegraph.models.ChangeImpact`.
        """
        direct_callers = self.graph.get_callers(sym.qualified_name)
        transitive_callers = self._get_transitive_callers(sym.qualified_name)

        all_callers = list({c.qualified_name: c for c in direct_callers + transitive_callers}.values())
        affected_files = self._collect_affected_files(all_callers)
        blast_radius = self._compute_blast_radius(len(all_callers))

        return ChangeImpact(
            symbol=sym,
            direct_callers=direct_callers,
            transitive_callers=transitive_callers,
            affected_files=affected_files,
            blast_radius=blast_radius,
        )

    def _get_transitive_callers(
        self,
        symbol_name: str,
        max_depth: int = 3,
    ) -> list[Symbol]:
        """BFS traversal to collect all callers up to *max_depth* hops away.

        The BFS starts from the immediate callers of ``symbol_name`` (depth 1)
        and fans out, tracking visited nodes to avoid cycles.

        Args:
            symbol_name: Qualified name of the root symbol.
            max_depth: Maximum number of hops to follow.  Defaults to ``3``.

        Returns:
            De-duplicated list of :class:`~codegraph.models.Symbol` objects
            reachable within ``max_depth`` hops.  Direct callers (depth 1) are
            included.
        """
        visited: set[str] = {symbol_name}
        result: list[Symbol] = []

        # Queue entries: (qualified_name, current_depth)
        queue: deque[tuple[str, int]] = deque()

        # Seed with direct callers at depth 1
        for caller in self.graph.get_callers(symbol_name):
            if caller.qualified_name not in visited:
                visited.add(caller.qualified_name)
                queue.append((caller.qualified_name, 1))
                result.append(caller)

        while queue:
            current_name, depth = queue.popleft()

            if depth >= max_depth:
                continue

            for caller in self.graph.get_callers(current_name):
                if caller.qualified_name not in visited:
                    visited.add(caller.qualified_name)
                    queue.append((caller.qualified_name, depth + 1))
                    result.append(caller)

        return result

    def _compute_blast_radius(self, caller_count: int) -> str:
        """Map a total caller count to a qualitative blast-radius label.

        Thresholds:

        * ``> 20`` callers  → ``"CRITICAL"``
        * ``6 – 20`` callers → ``"HIGH"``
        * ``1 – 5`` callers  → ``"MEDIUM"``
        * ``0`` callers      → ``"LOW"``

        Args:
            caller_count: Total number of unique callers (direct + transitive).

        Returns:
            One of ``"LOW"``, ``"MEDIUM"``, ``"HIGH"``, or ``"CRITICAL"``.
        """
        for threshold, label in _BLAST_THRESHOLDS:
            if caller_count >= threshold:
                return label
        return "LOW"  # fallback; unreachable given threshold list

    def _collect_affected_files(self, symbols: list[Symbol]) -> list[str]:
        """Collect unique file paths from a list of symbols.

        Args:
            symbols: Any iterable of :class:`~codegraph.models.Symbol` objects.

        Returns:
            Sorted list of unique ``file_path`` values from the input symbols.
        """
        seen: set[str] = set()
        result: list[str] = []
        for sym in symbols:
            if sym.file_path not in seen:
                seen.add(sym.file_path)
                result.append(sym.file_path)
        return sorted(result)
