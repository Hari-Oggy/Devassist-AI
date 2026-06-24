"""
Parser sub-package for CodeGraph.

:class:`ParserFactory` is the single entry-point for the rest of the
codebase.  Pass a file path and get back the right parser — or ``None``
when the file type is not supported.

Supported extensions
--------------------
* **Python** — ``.py``  →  :class:`PythonParser` (built-in :mod:`ast`)
* **JS / TS / Java / Rust / Go / C / C++** — see
  :data:`TREESITTER_EXTENSIONS`  →  :class:`TreeSitterParser`

Example::

    from codegraph.parsers import ParserFactory

    parser = ParserFactory.get_parser("src/utils.py")
    if parser:
        symbols, deps = parser.parse("src/utils.py", open("src/utils.py").read())
"""

from __future__ import annotations

import os

from codegraph.parsers.base_parser import BaseParser
from codegraph.parsers.python_parser import PythonParser
from codegraph.parsers.treesitter_parser import TreeSitterParser

# ---------------------------------------------------------------------------
# Extension sets
# ---------------------------------------------------------------------------

PYTHON_EXTENSIONS: frozenset[str] = frozenset({".py"})

TREESITTER_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".java",
        ".rs",
        ".go",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
    }
)

_ALL_SUPPORTED: frozenset[str] = PYTHON_EXTENSIONS | TREESITTER_EXTENSIONS


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class ParserFactory:
    """Static factory that maps file extensions to their parser instances.

    Parser objects are **not** cached because they are stateless; callers
    should cache the return value themselves if they will parse many files
    with the same parser.

    Example::

        parser = ParserFactory.get_parser("app/main.py")
        if parser is None:
            raise ValueError("Unsupported file type")
        symbols, deps = parser.parse("app/main.py", source)
    """

    @staticmethod
    def get_parser(file_path: str) -> BaseParser | None:
        """Return the appropriate parser for *file_path*, or ``None``.

        The parser is selected exclusively by file extension (case-insensitive).
        The file does not need to exist on disk.

        Args:
            file_path: Any path string whose extension determines the parser.
                The extension is extracted with :func:`os.path.splitext` so
                both ``"src/utils.py"`` and ``"utils.PY"`` are accepted.

        Returns:
            A :class:`~codegraph.parsers.base_parser.BaseParser` instance
            appropriate for the file type, or ``None`` when the extension is
            not in either :data:`PYTHON_EXTENSIONS` or
            :data:`TREESITTER_EXTENSIONS`.
        """
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()

        if ext in PYTHON_EXTENSIONS:
            return PythonParser()
        if ext in TREESITTER_EXTENSIONS:
            return TreeSitterParser()
        return None

    @staticmethod
    def is_supported(file_path: str) -> bool:
        """Return ``True`` if *file_path* can be parsed for symbols.

        Args:
            file_path: Any path string; only the extension is examined.

        Returns:
            ``True`` when the extension belongs to a supported language,
            ``False`` otherwise (including files with no extension).
        """
        _, ext = os.path.splitext(file_path)
        return ext.lower() in _ALL_SUPPORTED


__all__ = [
    "ParserFactory",
    "BaseParser",
    "PythonParser",
    "TreeSitterParser",
    "PYTHON_EXTENSIONS",
    "TREESITTER_EXTENSIONS",
]
