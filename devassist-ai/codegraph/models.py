"""Core dataclasses and enums for the CodeGraph static analysis package.

This module is intentionally free of heavy dependencies so it can be imported
by every other codegraph sub-module without circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SymbolKind(str, Enum):
    """Classification of a symbol discovered during static analysis.

    Inherits from ``str`` so that instances serialise naturally to JSON strings.
    """

    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    IMPORT = "import"
    MODULE = "module"
    CONSTANT = "constant"


@dataclass
class Symbol:
    """A named, addressable entity discovered in source code.

    Attributes:
        name: The bare (unqualified) identifier, e.g. ``"parse"``.
        kind: The :class:`SymbolKind` that classifies this symbol.
        file_path: Relative path from the repository root to the source file.
        line_start: 1-indexed line on which the symbol definition begins.
        line_end: 1-indexed line on which the symbol definition ends.
        qualified_name: Fully-qualified dotted name, e.g. ``"codegraph.parser.parse"``.
        signature: Optional human-readable signature string, e.g. ``"(source: str) -> AST"``.
        docstring: The first docstring paragraph extracted from the symbol, if any.
        is_exported: ``True`` when the symbol is part of the public API (no leading
            underscore, and either top-level or listed in ``__all__``).
    """

    name: str
    kind: SymbolKind
    file_path: str
    line_start: int
    line_end: int
    qualified_name: str
    signature: Optional[str] = None
    docstring: Optional[str] = None
    is_exported: bool = True


@dataclass
class Dependency:
    """A directed usage edge between two symbols in the graph.

    Attributes:
        source: Qualified name of the symbol that *uses* ``target``.
        target: Qualified name of the symbol being *used*.
        kind: Human-readable relationship label, e.g. ``"call"``, ``"import"``,
            ``"inherit"``, ``"type_ref"``.
        file_path: Relative path of the file where this dependency was recorded.
        line: 1-indexed source line where the dependency occurs.
    """

    source: str
    target: str
    kind: str
    file_path: str
    line: int


@dataclass
class ChangeImpact:
    """Impact record for a single symbol that was modified in a pull request.

    Attributes:
        symbol: The :class:`Symbol` that changed.
        direct_callers: Symbols that *directly* call / import ``symbol``.
        transitive_callers: All symbols reachable by following caller edges
            up to the configured BFS depth limit.
        affected_files: Unique file paths that contain at least one caller.
        blast_radius: Qualitative risk label — one of ``"LOW"``, ``"MEDIUM"``,
            ``"HIGH"``, or ``"CRITICAL"``.
    """

    symbol: Symbol
    direct_callers: list[Symbol] = field(default_factory=list)
    transitive_callers: list[Symbol] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    blast_radius: str = "LOW"


@dataclass
class ImpactReport:
    """Aggregated impact analysis result for an entire pull request.

    Attributes:
        pr_number: The GitHub pull-request number being analysed.
        changed_symbols: :class:`ChangeImpact` records for every symbol that
            changed, keyed by qualified name for O(1) access.
        breaking_changes: List of structured dicts describing potentially
            breaking API changes, e.g.
            ``{"type": "function_change", "function": "...", "description": "..."}``.
        high_risk_changes: Subset of ``changed_symbols`` whose ``blast_radius``
            is ``"HIGH"`` or ``"CRITICAL"``.
        affected_files: Union of all file paths touched by caller chains
            across every changed symbol.
        blast_radius: Overall PR blast-radius label (worst-case across all
            individual symbol blast radii).
        analysis_errors: Non-fatal error messages collected during analysis so
            that partial results are still usable.
    """

    pr_number: int
    changed_symbols: dict[str, ChangeImpact] = field(default_factory=dict)
    breaking_changes: list[dict] = field(default_factory=list)
    high_risk_changes: list[ChangeImpact] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    blast_radius: str = "LOW"
    analysis_errors: list[str] = field(default_factory=list)

    def max_blast_radius(self) -> str:
        """Return the worst-case blast radius across all changed symbols.

        Returns:
            One of ``"LOW"``, ``"MEDIUM"``, ``"HIGH"``, ``"CRITICAL"``,
            or ``"UNKNOWN"`` when no symbols were analysed.
        """
        _order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        worst = "UNKNOWN"
        for impact in self.changed_symbols.values():
            if worst == "UNKNOWN" or _order.get(impact.blast_radius, -1) > _order.get(worst, -1):
                worst = impact.blast_radius
        return worst

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dictionary representation of the report.

        Returns:
            Dict with keys: ``pr_number``, ``blast_radius``, ``affected_files``,
            ``breaking_changes``, ``high_risk_changes``, ``analysis_errors``,
            and ``changed_symbols`` (list of summary dicts).
        """
        return {
            "pr_number": self.pr_number,
            "blast_radius": self.blast_radius,
            "affected_files": list(self.affected_files),
            "breaking_changes": list(self.breaking_changes),
            "high_risk_changes": [
                {
                    "function": ci.symbol.qualified_name,
                    "callers_count": len(ci.direct_callers),
                    "blast_radius": ci.blast_radius,
                }
                for ci in self.high_risk_changes
            ],
            "changed_symbols": [
                {
                    "symbol": qname,
                    "blast_radius": ci.blast_radius,
                    "direct_callers": len(ci.direct_callers),
                    "transitive_callers": len(ci.transitive_callers),
                    "affected_files": ci.affected_files,
                }
                for qname, ci in self.changed_symbols.items()
            ],
            "analysis_errors": list(self.analysis_errors),
        }

