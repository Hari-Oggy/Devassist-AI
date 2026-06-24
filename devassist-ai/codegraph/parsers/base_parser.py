"""
Abstract base parser for all language-specific AST extractors.

Every concrete parser (PythonParser, TreeSitterParser, …) must subclass
:class:`BaseParser` and implement :meth:`extract_symbols` and
:meth:`extract_dependencies`. The concrete ``parse()`` helper calls both
methods with graceful per-method error isolation so that a crash in one
extraction phase never silently drops the other phase's results.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from codegraph.models import Dependency, Symbol


class BaseParser(ABC):
    """Abstract base for all language-specific AST parsers.

    Each parser extracts :class:`~codegraph.models.Symbol` definitions and
    :class:`~codegraph.models.Dependency` edges from source files for the
    CodeGraph.

    Implementors **must** override :meth:`extract_symbols` and
    :meth:`extract_dependencies`. The shared :meth:`parse` entry-point
    wraps both calls with individual ``try/except`` blocks so that a parse
    failure in one phase does not mask valid results from the other.
    """

    # ------------------------------------------------------------------
    # Abstract interface — subclasses must implement these two methods
    # ------------------------------------------------------------------

    @abstractmethod
    def extract_symbols(self, file_path: str, source: str) -> list[Symbol]:
        """Extract all symbol definitions from source code.

        Args:
            file_path: Repository-relative path to the file.  This value is
                stored verbatim on every returned :class:`~codegraph.models.Symbol`
                so it must be consistent with how other parts of the graph
                address the same file.
            source: Raw source code string (UTF-8 decoded).

        Returns:
            List of :class:`~codegraph.models.Symbol` objects defined in
            *this* file.  Must not return symbols defined in other files.
        """
        ...  # pragma: no cover

    @abstractmethod
    def extract_dependencies(self, file_path: str, source: str) -> list[Dependency]:
        """Extract all dependency edges declared in source code.

        A *dependency* is a directed usage relationship: the ``source``
        symbol (caller / importer / subclass) depends on the ``target``
        symbol (callee / imported name / base class).

        Args:
            file_path: Repository-relative path to the file.  Stored
                verbatim on every returned :class:`~codegraph.models.Dependency`.
            source: Raw source code string (UTF-8 decoded).

        Returns:
            List of :class:`~codegraph.models.Dependency` objects
            representing all usages and imports found in this file.
        """
        ...  # pragma: no cover

    # ------------------------------------------------------------------
    # Shared entry-point — error-isolated, not meant to be overridden
    # ------------------------------------------------------------------

    def parse(
        self, file_path: str, source: str
    ) -> tuple[list[Symbol], list[Dependency]]:
        """Parse a file and return both symbols and dependency edges.

        Calls :meth:`extract_symbols` and :meth:`extract_dependencies`
        independently.  If either raises an exception the corresponding
        result list is returned as empty while the other phase's results
        are preserved.  Callers that need to surface individual errors
        should call :meth:`extract_symbols` and :meth:`extract_dependencies`
        directly.

        Args:
            file_path: Repository-relative path to the file.
            source: Raw source code string (UTF-8 decoded).

        Returns:
            A 2-tuple ``(symbols, dependencies)`` where each element is a
            (possibly empty) list of the respective type.
        """
        try:
            symbols: list[Symbol] = self.extract_symbols(file_path, source)
        except Exception:  # noqa: BLE001 — intentional catch-all for resilience
            symbols = []

        try:
            deps: list[Dependency] = self.extract_dependencies(file_path, source)
        except Exception:  # noqa: BLE001
            deps = []

        return symbols, deps
