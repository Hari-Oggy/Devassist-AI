"""Tree-sitter–powered parser for JS, TS, Java, Rust, Go, C, and C++.

Wraps the ``tree-sitter`` library and its pre-built language grammars to build
a concrete syntax tree, then walks it to extract symbols and dependency edges.

Graceful fallback
-----------------
If ``tree-sitter`` (or the ``tree-sitter-languages`` convenience bundle) is
not installed, ``TREE_SITTER_AVAILABLE`` is set to ``False`` and every public
method returns an empty list.  A single ``WARNING`` log is emitted the first
time the missing-dependency path is exercised so that CI / monitoring surfaces
the gap without crashing the process.

Supported languages
-------------------
``javascript``, ``typescript``, ``java``, ``rust``, ``go``, ``c``, ``cpp``

File extension mapping::

    .js  / .jsx  → javascript
    .ts  / .tsx  → typescript
    .java        → java
    .rs          → rust
    .go          → go
    .c   / .h    → c
    .cpp / .hpp  → cpp
"""

from __future__ import annotations

import os
from typing import Optional

from codegraph.models import Dependency, Symbol, SymbolKind
from codegraph.parsers.base_parser import BaseParser
from core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional tree-sitter import — graceful degradation if not installed
# ---------------------------------------------------------------------------

TREE_SITTER_AVAILABLE: bool = False
_TS_WARNED: bool = False  # emit the "not installed" warning only once

try:
    from tree_sitter import Language, Node, Parser as _TSParser  # type: ignore[import]

    try:
        # ``tree-sitter-languages`` provides pre-compiled grammars in a single wheel.
        import tree_sitter_languages as _tsl  # type: ignore[import]

        def _get_language(lang_name: str) -> "Language":
            """Load a ``Language`` object from the ``tree-sitter-languages`` bundle.

            Args:
                lang_name: Tree-sitter language name, e.g. ``'python'``.

            Returns:
                A :class:`tree_sitter.Language` ready for parser use.
            """
            return _tsl.get_language(lang_name)

        TREE_SITTER_AVAILABLE = True

    except ImportError:
        # Fallback: try the older per-language build approach.
        # Users may have built their grammars into a shared library manually.
        def _get_language(lang_name: str) -> "Language":  # type: ignore[misc]
            """Attempt to load a language via a locally-built shared library.

            Args:
                lang_name: Tree-sitter language name.

            Returns:
                A :class:`tree_sitter.Language` instance.

            Raises:
                RuntimeError: When no compiled library is found.
            """
            import ctypes
            so_candidates = [
                os.path.join(os.getcwd(), "build", "languages.so"),
                os.path.join(os.getcwd(), "build", "languages.dll"),
            ]
            for so in so_candidates:
                if os.path.exists(so):
                    return Language(so, lang_name)
            raise RuntimeError(
                f"tree-sitter grammar for '{lang_name}' not found. "
                "Install 'tree-sitter-languages' or build grammars manually."
            )

        TREE_SITTER_AVAILABLE = True

except ImportError:
    # tree-sitter itself is not installed — silently degrade.
    TREE_SITTER_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants — extension ↔ language mapping
# ---------------------------------------------------------------------------

#: Maps file extensions (lower-case, with leading dot) to tree-sitter language
#: names understood by ``tree-sitter-languages``.
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".rs": "rust",
    ".go": "go",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
}

#: Maps tree-sitter node *type* strings to the corresponding
#: :class:`~codegraph.models.SymbolKind`.
NODE_TYPE_TO_SYMBOL_KIND: dict[str, SymbolKind] = {
    # Functions
    "function_declaration": SymbolKind.FUNCTION,
    "function_definition": SymbolKind.FUNCTION,
    "arrow_function": SymbolKind.FUNCTION,
    "function_expression": SymbolKind.FUNCTION,
    "method_declaration": SymbolKind.METHOD,
    "method_definition": SymbolKind.METHOD,
    "constructor_declaration": SymbolKind.METHOD,
    # Classes
    "class_declaration": SymbolKind.CLASS,
    "class_definition": SymbolKind.CLASS,
    # Imports
    "import_declaration": SymbolKind.IMPORT,
    "import_statement": SymbolKind.IMPORT,
    "use_declaration": SymbolKind.IMPORT,  # Rust
    "package_clause": SymbolKind.IMPORT,  # Go
    "include_statement": SymbolKind.IMPORT,  # C/C++
    "preproc_include": SymbolKind.IMPORT,  # C/C++
}

#: Symbolic node types that produce dependency edges of kind ``'import'``.
_IMPORT_NODE_TYPES: frozenset[str] = frozenset(
    {
        "import_declaration",
        "import_statement",
        "use_declaration",
        "preproc_include",
        "include_statement",
    }
)

#: Symbolic node types that produce dependency edges of kind ``'call'``.
_CALL_NODE_TYPES: frozenset[str] = frozenset(
    {
        "call_expression",
        "method_invocation",
        "function_call",
        "invocation_expression",
    }
)

#: Symbolic node types that produce dependency edges of kind ``'inherit'``.
_INHERIT_NODE_TYPES: frozenset[str] = frozenset(
    {
        "superclass",
        "base_class",
        "class_heritage",
        "extends_clause",
        "implements_clause",
        "supertypes",
    }
)


# ---------------------------------------------------------------------------
# Internal tree-walking utilities
# ---------------------------------------------------------------------------


def _file_to_module(file_path: str) -> str:
    """Convert a relative file path to a dotted module name.

    Args:
        file_path: Relative path to the source file.

    Returns:
        Dotted module string derived by stripping the file extension and
        replacing path separators with dots.
    """
    normalised = file_path.replace("\\", "/").lstrip("./")
    root, _ = os.path.splitext(normalised)
    return root.replace("/", ".")


def _node_text(node: "Node", source_bytes: bytes) -> str:
    """Extract the UTF-8 text covered by *node* from *source_bytes*.

    Args:
        node: A tree-sitter :class:`Node`.
        source_bytes: The full source file encoded as bytes.

    Returns:
        Decoded text slice, or an empty string on any decoding error.
    """
    try:
        return source_bytes[node.start_byte: node.end_byte].decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _find_identifier(node: "Node", source_bytes: bytes) -> str:
    """Return the first ``identifier`` child text found in *node*.

    Searches the immediate children only (depth = 1) to avoid accidentally
    picking up identifiers from deeply nested sub-trees.

    Args:
        node: A tree-sitter :class:`Node` whose name we want to resolve.
        source_bytes: Full source bytes for text extraction.

    Returns:
        The identifier text, or ``"<anonymous>"`` when none is found.
    """
    for child in node.children:
        if child.type == "identifier":
            return _node_text(child, source_bytes)
        # TypeScript / Java property_identifier
        if child.type in ("property_identifier", "type_identifier"):
            return _node_text(child, source_bytes)
    return "<anonymous>"


def _walk(node: "Node"):
    """Yield *node* and every descendant in depth-first order.

    Args:
        node: The root tree-sitter :class:`Node` to walk.

    Yields:
        Every :class:`Node` in the subtree, root-first.
    """
    yield node
    for child in node.children:
        yield from _walk(child)


def _warn_unavailable() -> None:
    """Emit a single warning that tree-sitter is not installed."""
    global _TS_WARNED  # noqa: PLW0603
    if not _TS_WARNED:
        logger.warning(
            "tree-sitter is not installed — TreeSitterParser will return empty results. "
            "Install it with: pip install tree-sitter tree-sitter-languages",
            extra={"warning": "tree_sitter_unavailable"},
        )
        _TS_WARNED = True


# ---------------------------------------------------------------------------
# Public parser class
# ---------------------------------------------------------------------------


class TreeSitterParser(BaseParser):
    """Tree-sitter–powered parser for JS, TS, Java, Rust, Go, C, and C++.

    The parser is language-agnostic at the class level: the correct grammar is
    selected either at construction time (via the *language* parameter) or
    dynamically at parse time from the file extension.

    When ``tree-sitter`` is not installed the class degrades gracefully:
    :meth:`extract_symbols` and :meth:`extract_dependencies` return empty lists
    and a one-time ``WARNING`` is logged.

    Attributes:
        EXTENSION_MAP: Class-level dict mapping file extensions to language names.

    Example::

        >>> parser = TreeSitterParser.for_file("src/index.ts")
        >>> if parser:
        ...     symbols, deps = parser.parse("src/index.ts", source_code)
        ...     print([s.kind.value for s in symbols])
        ['class', 'function', 'method']
    """

    #: Public alias for module-level constant (used by :meth:`for_file`).
    EXTENSION_MAP: dict[str, str] = EXTENSION_TO_LANGUAGE

    def __init__(self, language: Optional[str] = None) -> None:
        """Initialise a ``TreeSitterParser`` for a specific or auto-detected language.

        Args:
            language: Optional tree-sitter language name (e.g. ``'typescript'``).
                When ``None`` the language is inferred from the file extension
                on every :meth:`extract_symbols` / :meth:`extract_dependencies`
                call.
        """
        self._language_name: Optional[str] = language

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def for_file(cls, file_path: str) -> "TreeSitterParser | None":
        """Return a configured ``TreeSitterParser`` for *file_path*, or ``None``.

        The language is determined exclusively by the file extension.

        Args:
            file_path: Path to the source file (only the extension matters).

        Returns:
            A :class:`TreeSitterParser` instance pre-configured for the
            detected language, or ``None`` when the extension is not in
            :attr:`EXTENSION_MAP`.
        """
        _, ext = os.path.splitext(file_path)
        lang = EXTENSION_TO_LANGUAGE.get(ext.lower())
        if lang is None:
            return None
        return cls(language=lang)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_language(self, file_path: str) -> Optional[str]:
        """Resolve the tree-sitter language name for *file_path*.

        Uses the constructor-supplied *language* when available, otherwise
        looks up the extension in :attr:`EXTENSION_MAP`.

        Args:
            file_path: Path to the source file.

        Returns:
            Language name string, or ``None`` when the file type is unsupported.
        """
        if self._language_name:
            return self._language_name
        _, ext = os.path.splitext(file_path)
        return EXTENSION_TO_LANGUAGE.get(ext.lower())

    def _build_parser(self, lang_name: str) -> Optional["_TSParser"]:
        """Construct and return a tree-sitter ``Parser`` for *lang_name*.

        Args:
            lang_name: Tree-sitter language name, e.g. ``'rust'``.

        Returns:
            A ready-to-use tree-sitter :class:`Parser`, or ``None`` when the
            grammar cannot be loaded (logs a warning in that case).
        """
        try:
            language = _get_language(lang_name)
            parser = _TSParser()
            parser.set_language(language)
            return parser
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "TreeSitterParser: could not load grammar for '%s' — %s",
                lang_name,
                exc,
                extra={"language": lang_name, "error": str(exc)},
            )
            return None

    # ------------------------------------------------------------------
    # Symbol extraction
    # ------------------------------------------------------------------

    def extract_symbols(self, file_path: str, source: str) -> list[Symbol]:
        """Extract symbol definitions from a non-Python source file.

        Builds a concrete syntax tree with tree-sitter and collects nodes whose
        type maps to a :class:`~codegraph.models.SymbolKind`.  Covered node
        types vary per language but generally include:

        * ``function_declaration`` / ``function_definition`` → FUNCTION
        * ``class_declaration`` / ``class_definition`` → CLASS
        * ``method_declaration`` / ``method_definition`` → METHOD
        * ``import_statement`` / ``import_declaration`` → IMPORT

        Args:
            file_path: Repository-relative path to the source file.
            source: Raw UTF-8 source text.

        Returns:
            List of :class:`~codegraph.models.Symbol` instances.  Returns an
            empty list when tree-sitter is unavailable or parsing fails.
        """
        if not TREE_SITTER_AVAILABLE:
            _warn_unavailable()
            return []

        lang_name = self._resolve_language(file_path)
        if not lang_name:
            logger.debug(
                "TreeSitterParser: unsupported extension for '%s'", file_path
            )
            return []

        parser = self._build_parser(lang_name)
        if parser is None:
            return []

        try:
            source_bytes = source.encode("utf-8", errors="replace")
            tree = parser.parse(source_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "TreeSitterParser: parse failed for '%s' — %s",
                file_path,
                exc,
                extra={"file": file_path, "error": str(exc)},
            )
            return []

        module_qname = _file_to_module(file_path)
        symbols: list[Symbol] = []

        for node in _walk(tree.root_node):
            kind = NODE_TYPE_TO_SYMBOL_KIND.get(node.type)
            if kind is None:
                continue

            name = _find_identifier(node, source_bytes)
            # tree-sitter lines are 0-based → convert to 1-based
            line_start = node.start_point[0] + 1
            line_end = node.end_point[0] + 1
            qualified_name = f"{module_qname}.{name}"
            is_exported = not name.startswith("_")

            symbols.append(
                Symbol(
                    name=name,
                    kind=kind,
                    file_path=file_path,
                    line_start=line_start,
                    line_end=line_end,
                    qualified_name=qualified_name,
                    signature=None,
                    docstring=None,
                    is_exported=is_exported,
                )
            )

        return symbols

    # ------------------------------------------------------------------
    # Dependency extraction
    # ------------------------------------------------------------------

    def extract_dependencies(self, file_path: str, source: str) -> list[Dependency]:
        """Extract dependency edges from a non-Python source file.

        Produces :class:`~codegraph.models.Dependency` edges for:

        * Import / use / include statements → ``kind='import'``
        * Function / method call expressions → ``kind='call'``
        * Class inheritance / extends / implements → ``kind='inherit'``

        Args:
            file_path: Repository-relative path to the source file.
            source: Raw UTF-8 source text.

        Returns:
            List of :class:`~codegraph.models.Dependency` instances.  Returns
            an empty list when tree-sitter is unavailable or parsing fails.
        """
        if not TREE_SITTER_AVAILABLE:
            _warn_unavailable()
            return []

        lang_name = self._resolve_language(file_path)
        if not lang_name:
            return []

        parser = self._build_parser(lang_name)
        if parser is None:
            return []

        try:
            source_bytes = source.encode("utf-8", errors="replace")
            tree = parser.parse(source_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "TreeSitterParser: parse failed for '%s' — %s",
                file_path,
                exc,
                extra={"file": file_path, "error": str(exc)},
            )
            return []

        module_qname = _file_to_module(file_path)
        deps: list[Dependency] = []

        for node in _walk(tree.root_node):
            # tree-sitter lines are 0-based → convert to 1-based
            line = node.start_point[0] + 1

            if node.type in _IMPORT_NODE_TYPES:
                target = _node_text(node, source_bytes).strip()
                deps.append(
                    Dependency(
                        source=module_qname,
                        target=target,
                        kind="import",
                        file_path=file_path,
                        line=line,
                    )
                )

            elif node.type in _CALL_NODE_TYPES:
                # Try to extract the callee name from the first child
                callee = "<unknown>"
                if node.children:
                    first = node.children[0]
                    if first.type in ("identifier", "member_expression",
                                      "field_expression", "qualified_identifier"):
                        callee = _node_text(first, source_bytes)
                    else:
                        callee = _find_identifier(first, source_bytes)
                deps.append(
                    Dependency(
                        source=module_qname,
                        target=callee,
                        kind="call",
                        file_path=file_path,
                        line=line,
                    )
                )

            elif node.type in _INHERIT_NODE_TYPES:
                target_text = _node_text(node, source_bytes).strip()
                deps.append(
                    Dependency(
                        source=module_qname,
                        target=target_text,
                        kind="inherit",
                        file_path=file_path,
                        line=line,
                    )
                )

        return deps
