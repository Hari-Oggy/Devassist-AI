"""
AST-Aware Code Chunker — Phase 4 RAG component.

Unlike fixed-size sliding-window chunking (used in rag/indexer.py), this
module respects code structure: functions, classes, and methods are kept
as atomic units. Large bodies are split at logical sub-boundaries rather
than arbitrary character counts.

Supported languages:
    - Python (via stdlib ast module — zero dependencies)
    - JavaScript / TypeScript / Java / Rust / Go (regex-based heuristics)
    - Any other file type falls back to sliding-window chunking
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from core.logger import get_logger
from rag.rag_config import RAGSettings, get_rag_settings

logger = get_logger("rag.ast_chunker")


# ── Public data model ──────────────────────────────────────────────────


@dataclass
class CodeChunk:
    """A single chunk of source code ready for embedding.

    Attributes:
        content: The actual code text to embed.
        file_path: Relative or absolute path to the source file.
        start_line: 1-indexed start line in the original file.
        end_line: 1-indexed end line in the original file.
        chunk_type: What the chunk represents ('function', 'class', 'method',
            'module_header', 'block', 'text').
        symbol_name: Qualified name of the symbol if applicable.
        language: Detected language ('python', 'javascript', 'unknown').
        metadata: Extra key-value context for the vector store.
    """

    content: str
    file_path: str
    start_line: int = 0
    end_line: int = 0
    chunk_type: str = "block"          # function | class | method | module_header | block | text
    symbol_name: str = ""              # qualified name e.g. MyClass.my_method
    language: str = "unknown"
    metadata: dict = field(default_factory=dict)

    def to_metadata(self) -> dict:
        """Return a flat metadata dict suitable for vector store storage."""
        return {
            "source_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "chunk_type": self.chunk_type,
            "symbol_name": self.symbol_name,
            "language": self.language,
            **self.metadata,
        }


# ── Language detection ─────────────────────────────────────────────────


_EXT_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".md": "markdown",
    ".txt": "text",
}


def _detect_language(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    return _EXT_LANG.get(ext, "unknown")


# ── Main chunker class ─────────────────────────────────────────────────


class ASTChunker:
    """AST-aware code chunker that preserves symbol boundaries.

    Usage::

        chunker = ASTChunker()
        chunks = chunker.chunk_file("/path/to/file.py", source_code)

    The returned :class:`CodeChunk` objects include rich metadata (symbol
    name, line range, chunk type) that significantly improves retrieval
    relevance compared to fixed-size splitting.
    """

    def __init__(self, settings: Optional[RAGSettings] = None) -> None:
        self._cfg = settings or get_rag_settings()
        self._max_lines = self._cfg.RAG_AST_MAX_CHUNK_LINES
        self._sliding_size = self._cfg.RAG_CHUNK_SIZE
        self._sliding_overlap = self._cfg.RAG_CHUNK_OVERLAP

    # ── Public API ─────────────────────────────────────────────────────

    def chunk_file(self, file_path: str, source: str) -> list[CodeChunk]:
        """Chunk a source file into AST-aware or fallback sliding-window chunks.

        Args:
            file_path: Path to the source file (used for language detection).
            source: Raw source code text.

        Returns:
            List of :class:`CodeChunk` objects.
        """
        if not source or not source.strip():
            return []

        lang = _detect_language(file_path)

        try:
            if lang == "python":
                return self._chunk_python(file_path, source)
            elif lang in ("javascript", "typescript", "java", "go", "rust", "c", "cpp"):
                return self._chunk_generic(file_path, source, lang)
            else:
                return self._chunk_sliding(file_path, source, lang)
        except Exception as exc:
            logger.warning(
                "AST chunking failed for %s (%s): %s — using sliding fallback",
                file_path, lang, exc,
            )
            return self._chunk_sliding(file_path, source, lang)

    def chunk_files(self, files: list[dict]) -> list[CodeChunk]:
        """Chunk multiple files.

        Args:
            files: List of dicts with keys ``'file_path'`` and ``'content'``.

        Returns:
            Flat list of :class:`CodeChunk` from all files.
        """
        all_chunks: list[CodeChunk] = []
        for f in files:
            chunks = self.chunk_file(f["file_path"], f.get("content", ""))
            all_chunks.extend(chunks)
        return all_chunks

    # ── Python AST chunking ────────────────────────────────────────────

    def _chunk_python(self, file_path: str, source: str) -> list[CodeChunk]:
        """Chunk Python source using the stdlib ast module.

        Strategy:
            1. Module docstring + imports become a single 'module_header' chunk.
            2. Each top-level class → 'class' chunk (overview: class def + docstring only).
            3. Each method inside a class → 'method' chunk.
            4. Each top-level function → 'function' chunk.
            5. Remaining top-level code → 'block' chunk.

        Chunks exceeding ``_max_lines`` are split at sub-statement boundaries.
        """
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.debug("Python parse error %s: %s", file_path, exc)
            return self._chunk_sliding(file_path, source, "python")

        lines = source.splitlines()
        chunks: list[CodeChunk] = []

        # --- Module header: imports + module docstring ---
        header_lines = self._extract_module_header(tree, lines)
        if header_lines:
            chunks.append(CodeChunk(
                content="\n".join(header_lines),
                file_path=file_path,
                start_line=1,
                end_line=len(header_lines),
                chunk_type="module_header",
                language="python",
            ))

        # --- Top-level definitions ---
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunks.extend(self._make_function_chunks(node, lines, file_path, "python"))

            elif isinstance(node, ast.ClassDef):
                # Class overview chunk (signature + docstring)
                class_sig = self._class_signature(node, lines)
                chunks.append(CodeChunk(
                    content=class_sig,
                    file_path=file_path,
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    chunk_type="class",
                    symbol_name=node.name,
                    language="python",
                ))
                # Each method as its own chunk
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        chunks.extend(
                            self._make_function_chunks(
                                child, lines, file_path, "python",
                                class_prefix=node.name,
                            )
                        )

        if not chunks:
            return self._chunk_sliding(file_path, source, "python")

        return chunks

    def _extract_module_header(self, tree: ast.Module, lines: list[str]) -> list[str]:
        """Extract module docstring + import block lines."""
        header: list[str] = []
        for node in ast.iter_child_nodes(tree):
            # Only capture imports and the module docstring
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                end = node.end_lineno or node.lineno
                header.extend(lines[node.lineno - 1 : end])
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                # Module docstring is a standalone string expression at top
                if not header:  # only if it's at the very top
                    header.extend(lines[node.lineno - 1 : (node.end_lineno or node.lineno)])
            elif header:
                # Stop at the first non-import statement after imports started
                break
        return header

    def _make_function_chunks(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        lines: list[str],
        file_path: str,
        language: str,
        class_prefix: str = "",
    ) -> list[CodeChunk]:
        """Build chunk(s) from a function/method AST node."""
        start = node.lineno - 1
        end = (node.end_lineno or node.lineno) - 1
        func_lines = lines[start : end + 1]
        qualified = f"{class_prefix}.{node.name}" if class_prefix else node.name
        chunk_type = "method" if class_prefix else "function"

        if len(func_lines) <= self._max_lines:
            return [CodeChunk(
                content="\n".join(func_lines),
                file_path=file_path,
                start_line=start + 1,
                end_line=end + 1,
                chunk_type=chunk_type,
                symbol_name=qualified,
                language=language,
            )]

        # Split large functions into windows
        return self._split_lines_to_chunks(
            func_lines, file_path, start + 1, chunk_type, qualified, language,
        )

    def _class_signature(self, node: ast.ClassDef, lines: list[str]) -> str:
        """Return the class definition line + docstring (up to 10 lines)."""
        start = node.lineno - 1
        # Include up to 10 lines for the class header + docstring
        end = min(start + 10, (node.end_lineno or node.lineno) - 1)
        return "\n".join(lines[start : end + 1])

    # ── Generic regex-based chunking ───────────────────────────────────

    # Patterns to detect top-level function/class boundaries across languages
    _FUNC_PATTERNS: dict[str, re.Pattern] = {
        "javascript": re.compile(
            r"^(?:export\s+)?(?:async\s+)?(?:function\s+\w+|const\s+\w+\s*=\s*(?:async\s+)?\()",
            re.MULTILINE,
        ),
        "typescript": re.compile(
            r"^(?:export\s+)?(?:async\s+)?(?:function\s+\w+|const\s+\w+\s*=\s*(?:async\s+)?\(|class\s+\w+)",
            re.MULTILINE,
        ),
        "java": re.compile(
            r"^\s*(?:public|private|protected|static|final|abstract|\s)+\s+\w[\w<>\[\]]*\s+\w+\s*\(",
            re.MULTILINE,
        ),
        "go": re.compile(r"^func\s+", re.MULTILINE),
        "rust": re.compile(r"^(?:pub\s+)?(?:async\s+)?fn\s+", re.MULTILINE),
        "c": re.compile(r"^\w[\w\s\*]+\w\s*\([^;{]*\)\s*\{", re.MULTILINE),
        "cpp": re.compile(r"^\w[\w\s\*:~<>]+\w\s*\([^;]*\)\s*\{?", re.MULTILINE),
    }

    def _chunk_generic(self, file_path: str, source: str, language: str) -> list[CodeChunk]:
        """Regex-based chunking for non-Python languages.

        Splits at detected function/class boundaries. Falls back to
        sliding window if no boundaries are found.
        """
        pattern = self._FUNC_PATTERNS.get(language)
        if not pattern:
            return self._chunk_sliding(file_path, source, language)

        lines = source.splitlines()
        # Find line numbers of all boundaries
        boundaries: list[int] = [0]
        for m in pattern.finditer(source):
            line_no = source[:m.start()].count("\n")
            if line_no not in boundaries:
                boundaries.append(line_no)
        boundaries.append(len(lines))

        chunks: list[CodeChunk] = []
        for i in range(len(boundaries) - 1):
            s = boundaries[i]
            e = boundaries[i + 1]
            segment = lines[s:e]
            if not segment or not "".join(segment).strip():
                continue
            sub_chunks = self._split_lines_to_chunks(
                segment, file_path, s + 1, "block", "", language,
            )
            chunks.extend(sub_chunks)

        return chunks if chunks else self._chunk_sliding(file_path, source, language)

    # ── Sliding window fallback ────────────────────────────────────────

    def _chunk_sliding(self, file_path: str, source: str, language: str) -> list[CodeChunk]:
        """Fixed-size sliding-window chunking.

        Used as fallback for unsupported languages or when AST parsing fails.
        Preserves line-count context around each window.
        """
        lines = source.splitlines()
        step = max(1, self._max_lines - self._sliding_overlap // 40)
        chunks: list[CodeChunk] = []

        for start in range(0, len(lines), step):
            end = min(start + self._max_lines, len(lines))
            segment = lines[start:end]
            content = "\n".join(segment).strip()
            if content:
                chunks.append(CodeChunk(
                    content=content,
                    file_path=file_path,
                    start_line=start + 1,
                    end_line=end,
                    chunk_type="block",
                    language=language,
                ))
            if end >= len(lines):
                break

        return chunks

    # ── Utility ────────────────────────────────────────────────────────

    def _split_lines_to_chunks(
        self,
        lines: list[str],
        file_path: str,
        base_line: int,
        chunk_type: str,
        symbol_name: str,
        language: str,
    ) -> list[CodeChunk]:
        """Split a list of lines into max-size chunks."""
        chunks = []
        overlap = max(0, self._max_lines // 5)
        step = max(1, self._max_lines - overlap)

        for i in range(0, len(lines), step):
            segment = lines[i : i + self._max_lines]
            content = "\n".join(segment).strip()
            if content:
                chunks.append(CodeChunk(
                    content=content,
                    file_path=file_path,
                    start_line=base_line + i,
                    end_line=base_line + i + len(segment) - 1,
                    chunk_type=chunk_type,
                    symbol_name=symbol_name,
                    language=language,
                ))

        return chunks
