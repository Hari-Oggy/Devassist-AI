"""CodeGraph data container and builder.

This module provides two classes:

* :class:`CodeGraph` — an in-memory, read-only graph of symbols and
  dependencies produced from a repository scan.
* :class:`CodeGraphBuilder` — orchestrates file discovery, parser dispatch,
  and assembly of a :class:`CodeGraph`.

Typical usage::

    builder = CodeGraphBuilder(repo_path="/path/to/repo")
    graph   = builder.build()

    callers = graph.get_callers("mypackage.utils.helper")
"""

from __future__ import annotations

import os
from collections import defaultdict
from typing import TYPE_CHECKING

from core.logger import get_logger
from codegraph.models import Symbol, Dependency

if TYPE_CHECKING:
    # Avoid a hard dependency on the parser layer at import time so that
    # CodeGraph itself can be used without the full parser stack installed.
    from codegraph.parsers import ParserFactory  # type: ignore[import]

logger = get_logger("codegraph.graph_builder")

# Directories that are never worth analysing
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".git",
        "dist",
        "build",
        "migrations",
        ".mypy_cache",
        ".pytest_cache",
    }
)

# Files larger than this threshold are skipped to avoid OOM on huge generated files
_MAX_FILE_BYTES: int = 500 * 1024  # 500 KB


class CodeGraph:
    """An immutable, queryable graph of symbols and their dependencies.

    Instances are produced by :class:`CodeGraphBuilder` and consumed by
    :class:`~codegraph.impact_analyzer.ImpactAnalyzer` and other analysis
    components.

    Attributes:
        symbols: Mapping of qualified symbol name → :class:`~codegraph.models.Symbol`.
        dependencies: Ordered list of all :class:`~codegraph.models.Dependency` edges.
        file_to_symbols: Mapping of relative file path → list of qualified names
            of symbols defined in that file.
        repo_path: Absolute path to the root of the repository that was scanned.
    """

    def __init__(
        self,
        symbols: dict[str, Symbol],
        dependencies: list[Dependency],
        file_to_symbols: dict[str, list[str]],
        repo_path: str,
    ) -> None:
        """Initialise the graph with pre-built data structures.

        Args:
            symbols: Qualified-name keyed map of all discovered symbols.
            dependencies: All directed dependency edges.
            file_to_symbols: File-path keyed map of symbol qualified names.
            repo_path: Absolute repository root used during construction.
        """
        self.symbols: dict[str, Symbol] = symbols
        self.dependencies: list[Dependency] = dependencies
        self.file_to_symbols: dict[str, list[str]] = file_to_symbols
        self.repo_path: str = repo_path

        # Pre-build reverse-index structures for O(1) caller/callee lookup
        self._callers: dict[str, list[str]] = defaultdict(list)   # target  -> [source, ...]
        self._callees: dict[str, list[str]] = defaultdict(list)   # source  -> [target, ...]
        self._file_importers: dict[str, set[str]] = defaultdict(set)  # file -> {files that import it}

        for dep in self.dependencies:
            self._callers[dep.target].append(dep.source)
            self._callees[dep.source].append(dep.target)
            self._file_importers[dep.file_path]  # ensure key exists
            # Track which files import symbols from dep.file_path via target lookup
            if dep.target in self.symbols:
                target_file = self.symbols[dep.target].file_path
                if dep.file_path != target_file:
                    self._file_importers[target_file].add(dep.file_path)

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def get_symbols_in_file(self, file_path: str) -> list[Symbol]:
        """Return all symbols whose definition resides in *file_path*.

        Args:
            file_path: Relative path from the repository root.

        Returns:
            A list of :class:`~codegraph.models.Symbol` objects.  Empty list
            when no symbols are registered for the given file.
        """
        qualified_names = self.file_to_symbols.get(file_path, [])
        return [self.symbols[qn] for qn in qualified_names if qn in self.symbols]

    def get_callers(self, qualified_name: str) -> list[Symbol]:
        """Return symbols that *depend on* (call / import) ``qualified_name``.

        Args:
            qualified_name: The fully-qualified name of the symbol being queried.

        Returns:
            A list of :class:`~codegraph.models.Symbol` objects representing
            the callers.  Unknown callers (symbols not in the graph) are
            silently omitted.
        """
        caller_names = self._callers.get(qualified_name, [])
        return [self.symbols[n] for n in caller_names if n in self.symbols]

    def get_callees(self, qualified_name: str) -> list[Symbol]:
        """Return symbols that ``qualified_name`` *depends on* (calls / imports).

        Args:
            qualified_name: The fully-qualified name of the queried symbol.

        Returns:
            A list of :class:`~codegraph.models.Symbol` objects this symbol
            depends upon.  Unknown targets are silently omitted.
        """
        callee_names = self._callees.get(qualified_name, [])
        return [self.symbols[n] for n in callee_names if n in self.symbols]

    def get_files_depending_on(self, file_path: str) -> list[str]:
        """Return file paths that import at least one symbol from *file_path*.

        Args:
            file_path: Relative path from the repository root of the
                *imported* file.

        Returns:
            Sorted list of relative file paths that import from *file_path*.
        """
        return sorted(self._file_importers.get(file_path, set()))

    def symbol_count(self) -> int:
        """Return the total number of symbols in the graph.

        Returns:
            Integer count of unique symbols.
        """
        return len(self.symbols)

    def dependency_count(self) -> int:
        """Return the total number of dependency edges in the graph.

        Returns:
            Integer count of directed edges.
        """
        return len(self.dependencies)


class CodeGraphBuilder:
    """Walks a repository directory and builds a :class:`CodeGraph`.

    The builder delegates language-specific parsing to a
    :class:`~codegraph.parsers.factory.ParserFactory` (imported lazily so
    that the graph module can be used in isolation).

    Args:
        repo_path: Absolute path to the root of the repository to scan.
        parser_factory: Optional pre-constructed
            :class:`~codegraph.parsers.factory.ParserFactory` instance.
            When ``None`` the builder will attempt to import and instantiate
            ``codegraph.parsers.factory.ParserFactory`` on first use.

    Example::

        builder = CodeGraphBuilder("/repos/my-service")
        graph   = builder.build(max_files=200)
    """

    def __init__(
        self,
        repo_path: str,
        parser_factory: ParserFactory | None = None,
    ) -> None:
        self.repo_path: str = os.path.abspath(repo_path)
        self._parser_factory: ParserFactory | None = parser_factory

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_parser_factory(self) -> "ParserFactory":
        """Lazily import and return the ParserFactory singleton.

        Returns:
            A :class:`~codegraph.parsers.factory.ParserFactory` instance.

        Raises:
            ImportError: When the parsers sub-package is not available.
        """
        if self._parser_factory is None:
            from codegraph.parsers import ParserFactory  # type: ignore[import]
            self._parser_factory = ParserFactory()
        return self._parser_factory

    def _should_skip(self, path: str) -> bool:
        """Determine whether a path component should be excluded from scanning.

        Skips directories in :data:`_SKIP_DIRS` and files exceeding
        :data:`_MAX_FILE_BYTES`.

        Args:
            path: Absolute filesystem path to a file or directory.

        Returns:
            ``True`` if the path should be excluded from analysis.
        """
        parts = set(path.replace("\\", "/").split("/"))
        if parts & _SKIP_DIRS:
            return True
        if os.path.isfile(path) and os.path.getsize(path) > _MAX_FILE_BYTES:
            logger.info(
                "Skipping oversized file",
                extra={"path": path, "size_bytes": os.path.getsize(path)},
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Graph assembly helpers
    # ------------------------------------------------------------------

    def _make_empty_accumulators(
        self,
    ) -> tuple[dict[str, Symbol], list[Dependency], dict[str, list[str]]]:
        """Return fresh, empty accumulator structures for a build pass.

        Returns:
            A 3-tuple of ``(symbols, dependencies, file_to_symbols)``.
        """
        return {}, [], defaultdict(list)

    def _integrate_parse_result(
        self,
        rel_path: str,
        parse_result: object,
        symbols: dict[str, Symbol],
        dependencies: list[Dependency],
        file_to_symbols: dict[str, list[str]],
    ) -> None:
        """Merge a single parser output into the shared accumulators.

        The parser is expected to return an object with ``symbols`` and
        ``dependencies`` attributes (both iterables of the respective types).

        Args:
            rel_path: Relative path of the parsed file (for logging only).
            parse_result: Object returned by a language parser's ``parse()``
                method.
            symbols: Accumulator dict for all symbols, mutated in place.
            dependencies: Accumulator list for all edges, mutated in place.
            file_to_symbols: Accumulator mapping file → symbol names, mutated
                in place.
        """
        for sym in getattr(parse_result, "symbols", []):
            symbols[sym.qualified_name] = sym
            file_to_symbols[sym.file_path].append(sym.qualified_name)
        for dep in getattr(parse_result, "dependencies", []):
            dependencies.append(dep)

    def _parse_file(
        self,
        abs_path: str,
        rel_path: str,
        symbols: dict[str, Symbol],
        dependencies: list[Dependency],
        file_to_symbols: dict[str, list[str]],
    ) -> bool:
        """Attempt to parse a single file and integrate results.

        Args:
            abs_path: Absolute filesystem path to the source file.
            rel_path: Path relative to :attr:`repo_path`.
            symbols: Mutable accumulator for symbols.
            dependencies: Mutable accumulator for dependency edges.
            file_to_symbols: Mutable accumulator mapping file → symbol names.

        Returns:
            ``True`` when the file was parsed successfully, ``False``
            on any recoverable error (read failure, unsupported type, etc.).
        """
        factory = self._get_parser_factory()
        if not factory.is_supported(rel_path):
            return False

        try:
            source = abs_path
            with open(abs_path, encoding="utf-8", errors="replace") as fh:
                source = fh.read()
        except OSError as exc:
            logger.warning(
                "Could not read source file",
                extra={"path": rel_path, "error": str(exc)},
            )
            return False

        try:
            parser = factory.get_parser(rel_path)
            result = parser.parse(rel_path, source)
            self._integrate_parse_result(
                rel_path, result, symbols, dependencies, file_to_symbols
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Parser error — skipping file",
                extra={"path": rel_path, "error": str(exc)},
            )
            return False

    # ------------------------------------------------------------------
    # Public build API
    # ------------------------------------------------------------------

    def build(self, max_files: int = 500) -> CodeGraph:
        """Walk the entire repository and build a :class:`CodeGraph`.

        Directories matching :data:`_SKIP_DIRS` and files larger than
        :data:`_MAX_FILE_BYTES` are excluded automatically.

        Args:
            max_files: Hard upper limit on the number of files parsed.
                Prevents runaway analysis on very large mono-repos.

        Returns:
            A fully populated :class:`CodeGraph`.
        """
        symbols, dependencies, file_to_symbols = self._make_empty_accumulators()
        parsed_count = 0
        skipped_count = 0

        logger.info(
            "Starting full repository scan",
            extra={"repo_path": self.repo_path, "max_files": max_files},
        )

        for root, dirs, files in os.walk(self.repo_path, topdown=True):
            # Prune skipped directories in-place so os.walk won't descend
            dirs[:] = [
                d for d in dirs
                if not self._should_skip(os.path.join(root, d))
            ]

            for filename in files:
                if parsed_count >= max_files:
                    logger.info(
                        "Reached max_files limit — stopping scan",
                        extra={"max_files": max_files},
                    )
                    break

                abs_path = os.path.join(root, filename)
                if self._should_skip(abs_path):
                    skipped_count += 1
                    continue

                rel_path = os.path.relpath(abs_path, self.repo_path).replace("\\", "/")
                ok = self._parse_file(
                    abs_path, rel_path, symbols, dependencies, file_to_symbols
                )
                if ok:
                    parsed_count += 1
                else:
                    skipped_count += 1

        logger.info(
            "Repository scan complete",
            extra={
                "parsed": parsed_count,
                "skipped": skipped_count,
                "symbols": len(symbols),
                "dependencies": len(dependencies),
            },
        )

        return CodeGraph(
            symbols=symbols,
            dependencies=dependencies,
            file_to_symbols=dict(file_to_symbols),
            repo_path=self.repo_path,
        )

    def build_for_files(self, file_paths: list[str]) -> CodeGraph:
        """Build a :class:`CodeGraph` scoped to a specific list of files.

        Useful for PR-scoped analysis where only the files touched by a pull
        request need to be parsed (faster than a full repository scan).

        Args:
            file_paths: Relative (to :attr:`repo_path`) or absolute paths of
                the files to include in the graph.

        Returns:
            A :class:`CodeGraph` containing only the symbols and dependencies
            found in the specified files.
        """
        symbols, dependencies, file_to_symbols = self._make_empty_accumulators()

        logger.info(
            "Starting scoped file scan",
            extra={"file_count": len(file_paths), "repo_path": self.repo_path},
        )

        parsed_count = 0
        skipped_count = 0

        for fp in file_paths:
            # Resolve to absolute path
            abs_path = fp if os.path.isabs(fp) else os.path.join(self.repo_path, fp)
            abs_path = os.path.normpath(abs_path)

            if self._should_skip(abs_path) or not os.path.isfile(abs_path):
                skipped_count += 1
                continue

            rel_path = os.path.relpath(abs_path, self.repo_path).replace("\\", "/")
            ok = self._parse_file(
                abs_path, rel_path, symbols, dependencies, file_to_symbols
            )
            if ok:
                parsed_count += 1
            else:
                skipped_count += 1

        logger.info(
            "Scoped file scan complete",
            extra={
                "parsed": parsed_count,
                "skipped": skipped_count,
                "symbols": len(symbols),
                "dependencies": len(dependencies),
            },
        )

        return CodeGraph(
            symbols=symbols,
            dependencies=dependencies,
            file_to_symbols=dict(file_to_symbols),
            repo_path=self.repo_path,
        )
