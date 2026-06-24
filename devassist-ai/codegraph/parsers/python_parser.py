"""
Python AST Parser — extracts symbols and dependencies from .py files.

Uses Python's built-in :mod:`ast` module (no external deps required).

Extracts:
    Symbols:
        - Module-level functions (FUNCTION)
        - Classes (CLASS)
        - Methods inside classes (METHOD)
        - SCREAMING_SNAKE_CASE module-level assignments (CONSTANT)
        - Import aliases (IMPORT)

    Dependencies:
        - import / from...import statements (kind='import')
        - Function / method calls (kind='call')
        - Class inheritance (kind='inherit')

Usage::

    parser = PythonParser()
    symbols, deps = parser.parse("llm/router.py", source_code)
"""

from __future__ import annotations

import ast
import os
from typing import Optional

from codegraph.models import Dependency, Symbol, SymbolKind
from codegraph.parsers.base_parser import BaseParser


def _file_to_module(file_path: str) -> str:
    """Convert a file path to a Python module dotted name.

    Examples:
        ``llm/router.py``           →  ``llm.router``
        ``core/config.py``          →  ``core.config``
        ``agents/tools/linter.py``  →  ``agents.tools.linter``
    """
    # Normalise OS separators
    normalized = file_path.replace("\\", "/")
    # Strip leading ./
    normalized = normalized.lstrip("./")
    # Drop .py extension
    if normalized.endswith(".py"):
        normalized = normalized[:-3]
    # Replace path separators with dots
    return normalized.replace("/", ".")


def _node_end_line(node: ast.AST) -> int:
    """Return the last line of an AST node (1-based). Handles older Python."""
    if hasattr(node, "end_lineno") and node.end_lineno:
        return node.end_lineno
    # Fallback: same as start
    return getattr(node, "lineno", 1)


def _arg_to_str(arg: ast.arg) -> str:
    """Format a single argument including its annotation if present."""
    if arg.annotation:
        try:
            ann = ast.unparse(arg.annotation)
        except Exception:
            ann = "?"
        return f"{arg.arg}: {ann}"
    return arg.arg


def _build_signature(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Build a readable signature string from a FunctionDef node."""
    args = func.args
    parts: list[str] = []

    # positional-or-keyword args with defaults aligned from the right
    n_defaults = len(args.defaults)
    n_args = len(args.args)
    for i, arg in enumerate(args.args):
        default_idx = i - (n_args - n_defaults)
        if default_idx >= 0:
            try:
                default_str = ast.unparse(args.defaults[default_idx])
            except Exception:
                default_str = "..."
            parts.append(f"{_arg_to_str(arg)}={default_str}")
        else:
            parts.append(_arg_to_str(arg))

    if args.vararg:
        parts.append(f"*{_arg_to_str(args.vararg)}")
    if args.kwonlyargs:
        if not args.vararg:
            parts.append("*")
        for i, arg in enumerate(args.kwonlyargs):
            kw_default = args.kw_defaults[i]
            if kw_default is not None:
                try:
                    d = ast.unparse(kw_default)
                except Exception:
                    d = "..."
                parts.append(f"{_arg_to_str(arg)}={d}")
            else:
                parts.append(_arg_to_str(arg))
    if args.kwarg:
        parts.append(f"**{_arg_to_str(args.kwarg)}")

    sig = f"({', '.join(parts)})"

    # Return annotation
    if func.returns:
        try:
            sig += f" -> {ast.unparse(func.returns)}"
        except Exception:
            pass

    return sig


class _SymbolVisitor(ast.NodeVisitor):
    """AST visitor that collects Symbol definitions."""

    def __init__(self, module_name: str, file_path: str) -> None:
        self.module_name = module_name
        self.file_path = file_path
        self.symbols: list[Symbol] = []
        self._class_stack: list[str] = []  # tracks nesting for qualified names

    # ── Utilities ──────────────────────────────────────────────────────────

    def _qualified(self, name: str) -> str:
        if self._class_stack:
            return f"{self.module_name}.{'.'.join(self._class_stack)}.{name}"
        return f"{self.module_name}.{name}"

    # ── Visitors ───────────────────────────────────────────────────────────

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qname = self._qualified(node.name)
        self.symbols.append(
            Symbol(
                name=node.name,
                kind=SymbolKind.CLASS,
                file_path=self.file_path,
                line_start=node.lineno,
                line_end=_node_end_line(node),
                qualified_name=qname,
                docstring=ast.get_docstring(node) or "",
                is_exported=not node.name.startswith("_"),
                signature="",
            )
        )
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        kind = SymbolKind.METHOD if self._class_stack else SymbolKind.FUNCTION
        qname = self._qualified(node.name)
        self.symbols.append(
            Symbol(
                name=node.name,
                kind=kind,
                file_path=self.file_path,
                line_start=node.lineno,
                line_end=_node_end_line(node),
                qualified_name=qname,
                signature=_build_signature(node),
                docstring=ast.get_docstring(node) or "",
                is_exported=not node.name.startswith("_"),
            )
        )
        # Don't recurse into nested functions — keep the graph flat
        # but DO visit class bodies inside the function
        for child in ast.walk(node):
            if isinstance(child, ast.ClassDef):
                self.visit_ClassDef(child)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_func(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Capture SCREAMING_SNAKE_CASE module-level assignments as CONSTANT."""
        if self._class_stack:
            return  # Only module-level
        for target in node.targets:
            if isinstance(target, ast.Name):
                name = target.id
                if name.isupper() and "_" in name or (name.isupper() and len(name) > 2):
                    self.symbols.append(
                        Symbol(
                            name=name,
                            kind=SymbolKind.CONSTANT,
                            file_path=self.file_path,
                            line_start=node.lineno,
                            line_end=_node_end_line(node),
                            qualified_name=self._qualified(name),
                            is_exported=not name.startswith("_"),
                            signature="",
                            docstring="",
                        )
                    )
        self.generic_visit(node)


class _DependencyVisitor(ast.NodeVisitor):
    """AST visitor that collects Dependency edges."""

    def __init__(self, module_name: str, file_path: str) -> None:
        self.module_name = module_name
        self.file_path = file_path
        self.dependencies: list[Dependency] = []
        self._class_stack: list[str] = []
        self._func_stack: list[str] = []

    def _current_scope(self) -> str:
        parts = [self.module_name]
        if self._class_stack:
            parts.extend(self._class_stack)
        if self._func_stack:
            parts.append(self._func_stack[-1])
        return ".".join(parts)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Inheritance dependencies
        for base in node.bases:
            try:
                base_name = ast.unparse(base)
            except Exception:
                base_name = "?"
            self.dependencies.append(
                Dependency(
                    source=f"{self.module_name}.{node.name}",
                    target=base_name,
                    kind="inherit",
                    file_path=self.file_path,
                    line=node.lineno,
                )
            )
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.dependencies.append(
                Dependency(
                    source=self._current_scope(),
                    target=alias.name,
                    kind="import",
                    file_path=self.file_path,
                    line=node.lineno,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            target = f"{module}.{alias.name}" if module else alias.name
            self.dependencies.append(
                Dependency(
                    source=self._current_scope(),
                    target=target,
                    kind="import",
                    file_path=self.file_path,
                    line=node.lineno,
                )
            )

    def visit_Call(self, node: ast.Call) -> None:
        try:
            func_name = ast.unparse(node.func)
        except Exception:
            self.generic_visit(node)
            return
        self.dependencies.append(
            Dependency(
                source=self._current_scope(),
                target=func_name,
                kind="call",
                file_path=self.file_path,
                line=node.lineno,
            )
        )
        self.generic_visit(node)


class PythonParser(BaseParser):
    """Full AST-based parser for Python (.py) source files.

    Uses Python's built-in :mod:`ast` module — no external dependencies
    required. Extracts symbols and dependency edges for the CodeGraph.

    Example::

        parser = PythonParser()
        symbols, deps = parser.parse("mymodule/utils.py", source_code)
        [s.qualified_name for s in symbols]
        # ['mymodule.utils.helper', 'mymodule.utils.MyClass']
    """

    def extract_symbols(self, file_path: str, source: str) -> list[Symbol]:
        """Extract symbol definitions from a Python source file.

        Args:
            file_path: Repository-relative path to the .py file.
            source: Raw UTF-8 source text.

        Returns:
            List of Symbol instances for every top-level and class-level
            definition found in source.
        """
        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError:
            return []

        module_name = _file_to_module(file_path)
        visitor = _SymbolVisitor(module_name=module_name, file_path=file_path)
        visitor.visit(tree)
        return visitor.symbols

    def extract_dependencies(self, file_path: str, source: str) -> list[Dependency]:
        """Extract dependency edges from a Python source file.

        Args:
            file_path: Repository-relative path to the .py file.
            source: Raw UTF-8 source text.

        Returns:
            List of Dependency instances representing imports, calls,
            and inheritance edges found in source.
        """
        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError:
            return []

        module_name = _file_to_module(file_path)
        visitor = _DependencyVisitor(module_name=module_name, file_path=file_path)
        visitor.visit(tree)
        return visitor.dependencies
