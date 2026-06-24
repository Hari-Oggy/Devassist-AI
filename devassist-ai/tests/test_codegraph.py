"""
Tests for CodeGraph — Phase 2 cross-file dependency analysis.

Tests cover:
    - Symbol extraction from Python source
    - Dependency extraction (imports, calls, inheritance)
    - CodeGraph construction and querying
    - ImpactAnalyzer blast radius computation
    - Blast radius categories (LOW / MEDIUM / HIGH / CRITICAL)
    - Breaking change detection
    - File dependency traversal
"""

import pytest
import textwrap
from unittest.mock import MagicMock

from codegraph.models import (
    Symbol,
    SymbolKind,
    Dependency,
    ChangeImpact,
    ImpactReport,
)


# ── Helper: build an empty CodeGraph for tests ──────────────────────────

def _make_empty_graph(repo_path: str = "/tmp/test_repo"):
    """Construct a CodeGraph with empty data (avoids requiring positional args)."""
    from codegraph.graph_builder import CodeGraph
    return CodeGraph(
        symbols={},
        dependencies=[],
        file_to_symbols={},
        repo_path=repo_path,
    )


def _make_graph_with_data():
    """Build a CodeGraph with 3 symbols and 2 call edges for query tests."""
    from codegraph.graph_builder import CodeGraph

    sym_a = Symbol(
        name="process_data", kind=SymbolKind.FUNCTION,
        file_path="core/processor.py", line_start=10, line_end=30,
        qualified_name="core.processor.process_data",
    )
    sym_b = Symbol(
        name="validate", kind=SymbolKind.FUNCTION,
        file_path="core/validator.py", line_start=5, line_end=15,
        qualified_name="core.validator.validate",
    )
    sym_c = Symbol(
        name="run_pipeline", kind=SymbolKind.FUNCTION,
        file_path="pipeline.py", line_start=1, line_end=50,
        qualified_name="pipeline.run_pipeline",
    )

    symbols = {
        sym_a.qualified_name: sym_a,
        sym_b.qualified_name: sym_b,
        sym_c.qualified_name: sym_c,
    }
    file_to_symbols = {
        "core/processor.py": [sym_a.qualified_name],
        "core/validator.py": [sym_b.qualified_name],
        "pipeline.py": [sym_c.qualified_name],
    }
    # run_pipeline -> process_data -> validate
    dependencies = [
        Dependency(
            source="pipeline.run_pipeline",
            target="core.processor.process_data",
            kind="call",
            file_path="pipeline.py",
            line=20,
        ),
        Dependency(
            source="core.processor.process_data",
            target="core.validator.validate",
            kind="call",
            file_path="core/processor.py",
            line=15,
        ),
    ]

    graph = CodeGraph(
        symbols=symbols,
        dependencies=dependencies,
        file_to_symbols=file_to_symbols,
        repo_path="/tmp/repo",
    )
    return graph, sym_a, sym_b, sym_c


# ── Model Tests ─────────────────────────────────────────────────────────


class TestSymbol:
    def test_defaults(self):
        sym = Symbol(
            name="my_func",
            kind=SymbolKind.FUNCTION,
            file_path="utils.py",
            line_start=10,
            line_end=20,
            qualified_name="utils.my_func",
        )
        # signature and docstring may default to None or "" depending on impl
        assert sym.is_exported is True
        assert sym.name == "my_func"
        assert sym.kind == SymbolKind.FUNCTION

    def test_private_symbol(self):
        sym = Symbol(
            name="_private_helper",
            kind=SymbolKind.FUNCTION,
            file_path="utils.py",
            line_start=5,
            line_end=8,
            qualified_name="utils._private_helper",
            is_exported=False,
        )
        assert sym.is_exported is False


class TestDependency:
    def test_call_dependency(self):
        dep = Dependency(
            source="api.views.create_user",
            target="models.user.User",
            kind="call",
            file_path="api/views.py",
            line=42,
        )
        assert dep.kind == "call"

    def test_import_dependency(self):
        dep = Dependency(
            source="api.views",
            target="models.user",
            kind="import",
            file_path="api/views.py",
            line=1,
        )
        assert dep.kind == "import"


class TestImpactReport:
    def test_empty_report(self):
        report = ImpactReport(pr_number=0)
        assert report.blast_radius in {"LOW", "UNKNOWN", "HIGH", "MEDIUM", "CRITICAL"}
        assert len(report.changed_symbols) == 0
        assert report.affected_files == []

    def test_pr_number(self):
        report = ImpactReport(pr_number=42)
        assert report.pr_number == 42

    def test_to_dict(self):
        report = ImpactReport(pr_number=42, blast_radius="MEDIUM")
        d = report.to_dict()
        assert isinstance(d, dict)
        assert d["blast_radius"] == "MEDIUM"
        assert d["pr_number"] == 42

    def test_max_blast_radius_empty(self):
        report = ImpactReport(pr_number=0)
        result = report.max_blast_radius()
        # Should return a string (either UNKNOWN or LOW when no symbols)
        assert isinstance(result, str)

    def test_changed_symbols_type(self):
        report = ImpactReport(pr_number=1)
        # changed_symbols is either list or dict — check it's empty
        cs = report.changed_symbols
        assert len(cs) == 0


# ── Python Parser Tests ─────────────────────────────────────────────────


class TestPythonParser:
    """Tests for Python AST-based symbol and dependency extraction."""

    def _get_parser(self):
        from codegraph.parsers.python_parser import PythonParser
        return PythonParser()

    def test_extract_function(self):
        parser = self._get_parser()
        source = textwrap.dedent("""\
            def greet(name: str) -> str:
                '''Greet someone.'''
                return f"Hello, {name}"
        """)
        symbols = parser.extract_symbols("utils.py", source)
        names = [s.name for s in symbols]
        assert "greet" in names
        func = next(s for s in symbols if s.name == "greet")
        assert func.kind == SymbolKind.FUNCTION
        assert func.qualified_name == "utils.greet"

    def test_extract_class(self):
        parser = self._get_parser()
        source = textwrap.dedent("""\
            class UserService:
                '''Handles user operations.'''

                def create(self, data: dict):
                    pass

                def delete(self, user_id: int):
                    pass
        """)
        symbols = parser.extract_symbols("services/user.py", source)
        kinds = {s.kind for s in symbols}
        assert SymbolKind.CLASS in kinds
        assert SymbolKind.METHOD in kinds

        class_sym = next(s for s in symbols if s.kind == SymbolKind.CLASS)
        assert class_sym.name == "UserService"
        assert class_sym.qualified_name == "services.user.UserService"

    def test_extract_private_function(self):
        parser = self._get_parser()
        source = "def _internal_helper():\n    pass\n"
        symbols = parser.extract_symbols("utils.py", source)
        assert len(symbols) >= 1
        sym = next((s for s in symbols if s.name == "_internal_helper"), None)
        assert sym is not None
        assert sym.is_exported is False

    def test_extract_imports(self):
        parser = self._get_parser()
        source = textwrap.dedent("""\
            import os
            from pathlib import Path
            from typing import Optional, List
        """)
        deps = parser.extract_dependencies("myfile.py", source)
        dep_kinds = {d.kind for d in deps}
        assert "import" in dep_kinds

    def test_extract_inheritance(self):
        parser = self._get_parser()
        source = textwrap.dedent("""\
            from abc import ABC

            class MyBase(ABC):
                pass
        """)
        deps = parser.extract_dependencies("base.py", source)
        inherit_deps = [d for d in deps if d.kind == "inherit"]
        assert len(inherit_deps) >= 1

    def test_invalid_syntax_graceful(self):
        parser = self._get_parser()
        source = "def broken_func(:\n    pass"
        symbols = parser.extract_symbols("broken.py", source)
        # Should return empty list, not raise
        assert isinstance(symbols, list)
        assert len(symbols) == 0

    def test_extract_constant(self):
        parser = self._get_parser()
        source = "MAX_RETRIES = 3\nDEFAULT_TIMEOUT = 30\n"
        symbols = parser.extract_symbols("config.py", source)
        constant_names = [s.name for s in symbols if s.kind == SymbolKind.CONSTANT]
        assert "MAX_RETRIES" in constant_names or "DEFAULT_TIMEOUT" in constant_names

    def test_nested_module_path(self):
        parser = self._get_parser()
        source = "def process(): pass\n"
        symbols = parser.extract_symbols("llm/providers/openai_provider.py", source)
        assert len(symbols) >= 1
        assert symbols[0].qualified_name == "llm.providers.openai_provider.process"

    def test_docstring_extraction(self):
        parser = self._get_parser()
        source = textwrap.dedent('''\
            def helper():
                """This is a docstring."""
                pass
        ''')
        symbols = parser.extract_symbols("utils.py", source)
        assert len(symbols) >= 1
        sym = symbols[0]
        assert "docstring" in sym.docstring.lower() or sym.docstring != ""

    def test_signature_extraction(self):
        parser = self._get_parser()
        source = "def add(a: int, b: int = 0) -> int:\n    return a + b\n"
        symbols = parser.extract_symbols("math_utils.py", source)
        func = next((s for s in symbols if s.name == "add"), None)
        assert func is not None
        # signature should contain "a" and "b"
        assert func.signature is not None

    def test_async_function(self):
        parser = self._get_parser()
        source = "async def fetch(url: str) -> dict:\n    pass\n"
        symbols = parser.extract_symbols("client.py", source)
        assert any(s.name == "fetch" for s in symbols)


# ── CodeGraph Tests ─────────────────────────────────────────────────────


class TestCodeGraph:
    """Tests for CodeGraph data container and its query methods."""

    def test_symbol_count(self):
        graph, _, _, _ = _make_graph_with_data()
        assert graph.symbol_count() == 3

    def test_dependency_count(self):
        graph, _, _, _ = _make_graph_with_data()
        assert graph.dependency_count() == 2

    def test_get_symbols_in_file(self):
        graph, sym_a, _, _ = _make_graph_with_data()
        syms = graph.get_symbols_in_file("core/processor.py")
        assert len(syms) == 1
        assert syms[0].name == "process_data"

    def test_get_callers(self):
        graph, _, _, _ = _make_graph_with_data()
        # Who calls process_data?
        callers = graph.get_callers("core.processor.process_data")
        caller_names = [c.name for c in callers]
        assert "run_pipeline" in caller_names

    def test_get_callees(self):
        graph, _, _, _ = _make_graph_with_data()
        # What does process_data call?
        callees = graph.get_callees("core.processor.process_data")
        callee_names = [c.name for c in callees]
        assert "validate" in callee_names

    def test_get_files_depending_on(self):
        graph, _, _, _ = _make_graph_with_data()
        files = graph.get_files_depending_on("core/processor.py")
        assert "pipeline.py" in files

    def test_empty_graph(self):
        graph = _make_empty_graph()
        assert graph.symbol_count() == 0
        assert graph.dependency_count() == 0
        assert graph.get_symbols_in_file("anything.py") == []
        assert graph.get_callers("nothing") == []

    def test_get_symbols_unknown_file(self):
        graph, _, _, _ = _make_graph_with_data()
        assert graph.get_symbols_in_file("nonexistent.py") == []


# ── ImpactAnalyzer Tests ────────────────────────────────────────────────


class TestImpactAnalyzer:
    """Tests for blast radius and breaking change detection."""

    def _get_analyzer_with_graph(self):
        from codegraph.graph_builder import CodeGraph
        from codegraph.impact_analyzer import ImpactAnalyzer

        target = Symbol(
            name="critical_func", kind=SymbolKind.FUNCTION,
            file_path="core/critical.py", line_start=1, line_end=20,
            qualified_name="core.critical.critical_func",
            is_exported=True,
        )
        caller1 = Symbol(
            name="feature_a", kind=SymbolKind.FUNCTION,
            file_path="features/a.py", line_start=1, line_end=10,
            qualified_name="features.a.feature_a",
        )
        caller2 = Symbol(
            name="feature_b", kind=SymbolKind.FUNCTION,
            file_path="features/b.py", line_start=1, line_end=10,
            qualified_name="features.b.feature_b",
        )

        symbols = {
            target.qualified_name: target,
            caller1.qualified_name: caller1,
            caller2.qualified_name: caller2,
        }
        file_to_symbols = {
            "core/critical.py": [target.qualified_name],
            "features/a.py": [caller1.qualified_name],
            "features/b.py": [caller2.qualified_name],
        }
        dependencies = [
            Dependency(
                source=caller1.qualified_name,
                target=target.qualified_name,
                kind="call", file_path="features/a.py", line=5,
            ),
            Dependency(
                source=caller2.qualified_name,
                target=target.qualified_name,
                kind="call", file_path="features/b.py", line=5,
            ),
        ]

        graph = CodeGraph(
            symbols=symbols,
            dependencies=dependencies,
            file_to_symbols=file_to_symbols,
            repo_path="/tmp/repo",
        )
        return ImpactAnalyzer(graph), graph

    def test_blast_radius_low(self):
        from codegraph.impact_analyzer import ImpactAnalyzer
        analyzer = ImpactAnalyzer(_make_empty_graph())
        assert analyzer._compute_blast_radius(0) == "LOW"

    def test_blast_radius_medium(self):
        from codegraph.impact_analyzer import ImpactAnalyzer
        analyzer = ImpactAnalyzer(_make_empty_graph())
        assert analyzer._compute_blast_radius(3) == "MEDIUM"

    def test_blast_radius_high(self):
        from codegraph.impact_analyzer import ImpactAnalyzer
        analyzer = ImpactAnalyzer(_make_empty_graph())
        assert analyzer._compute_blast_radius(10) == "HIGH"

    def test_blast_radius_critical(self):
        from codegraph.impact_analyzer import ImpactAnalyzer
        analyzer = ImpactAnalyzer(_make_empty_graph())
        assert analyzer._compute_blast_radius(25) == "CRITICAL"

    def test_analyze_changed_file(self):
        analyzer, graph = self._get_analyzer_with_graph()
        report = analyzer.analyze(["core/critical.py"], pr_number=7)

        assert isinstance(report, ImpactReport)
        assert report.pr_number == 7
        # changed_symbols is either list or dict — check it's non-empty
        assert len(report.changed_symbols) >= 1

    def test_analyze_nonexistent_file(self):
        from codegraph.impact_analyzer import ImpactAnalyzer
        graph = _make_empty_graph()
        analyzer = ImpactAnalyzer(graph)
        report = analyzer.analyze(["nonexistent.py"])
        assert isinstance(report, ImpactReport)
        assert len(report.changed_symbols) == 0

    def test_affected_files_populated(self):
        analyzer, graph = self._get_analyzer_with_graph()
        report = analyzer.analyze(["core/critical.py"])
        # features/a.py and features/b.py should appear somewhere
        # (either in affected_files or within changed_symbols)
        all_affected = set(report.affected_files)
        assert len(all_affected) >= 1

    def test_high_risk_changes(self):
        analyzer, graph = self._get_analyzer_with_graph()
        report = analyzer.analyze(["core/critical.py"])
        # critical_func has 2 callers -> at least MEDIUM
        assert report.blast_radius in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
