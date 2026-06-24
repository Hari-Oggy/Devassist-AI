"""
Tests for Phase 4: Advanced RAG — AST Chunker, Hybrid Retriever, History Indexer.

All tests run without external dependencies (no FAISS, no sentence-transformers,
no rank-bm25 required). Heavy components are mocked so the test suite passes
in any CI environment.
"""

from __future__ import annotations

import json
import os
import tempfile
import textwrap
from unittest.mock import MagicMock, patch

import pytest

# ── RAGSettings ─────────────────────────────────────────────────────────


class TestRAGSettings:
    def test_defaults(self):
        from rag.rag_config import RAGSettings
        cfg = RAGSettings()
        assert cfg.RAG_CHUNK_STRATEGY == "ast"
        assert cfg.RAG_RETRIEVAL_MODE == "hybrid"
        assert cfg.RAG_HYBRID_ALPHA == 0.6
        assert cfg.RAG_RRF_K == 60
        assert cfg.RAG_FINAL_K == 5
        assert cfg.RAG_TOP_K == 10

    def test_code_extensions_property(self):
        from rag.rag_config import RAGSettings
        cfg = RAGSettings()
        exts = cfg.code_extensions
        assert ".py" in exts
        assert ".ts" in exts
        assert ".go" in exts

    def test_is_hybrid_property(self):
        from rag.rag_config import RAGSettings
        cfg = RAGSettings(RAG_RETRIEVAL_MODE="hybrid")
        assert cfg.is_hybrid is True

        cfg2 = RAGSettings(RAG_RETRIEVAL_MODE="dense")
        assert cfg2.is_hybrid is False

    def test_singleton(self):
        from rag.rag_config import get_rag_settings
        a = get_rag_settings()
        b = get_rag_settings()
        assert a is b


# ── ASTChunker — Python ─────────────────────────────────────────────────


class TestASTChunkerPython:
    def _chunker(self):
        from rag.ast_chunker import ASTChunker
        from rag.rag_config import RAGSettings
        return ASTChunker(settings=RAGSettings())

    def test_chunk_simple_function(self):
        chunker = self._chunker()
        src = textwrap.dedent("""\
            def add(a: int, b: int) -> int:
                '''Return sum.'''
                return a + b
        """)
        chunks = chunker.chunk_file("utils.py", src)
        assert len(chunks) >= 1
        types = [c.chunk_type for c in chunks]
        assert "function" in types or "module_header" in types or "block" in types

    def test_chunk_function_symbol_name(self):
        chunker = self._chunker()
        src = textwrap.dedent("""\
            def authenticate(user: str) -> bool:
                return True
        """)
        chunks = chunker.chunk_file("auth.py", src)
        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert any("authenticate" in c.symbol_name for c in func_chunks)

    def test_chunk_class_and_method(self):
        chunker = self._chunker()
        src = textwrap.dedent("""\
            class MyService:
                '''A service class.'''
                def process(self, data: dict) -> dict:
                    return data
                def validate(self, data: dict) -> bool:
                    return bool(data)
        """)
        chunks = chunker.chunk_file("service.py", src)
        types = {c.chunk_type for c in chunks}
        assert "class" in types or "method" in types

    def test_chunk_method_has_class_prefix(self):
        chunker = self._chunker()
        src = textwrap.dedent("""\
            class Auth:
                def login(self, user: str) -> bool:
                    return True
        """)
        chunks = chunker.chunk_file("auth.py", src)
        method_chunks = [c for c in chunks if c.chunk_type == "method"]
        if method_chunks:
            assert any("Auth" in c.symbol_name for c in method_chunks)

    def test_chunk_preserves_file_path(self):
        chunker = self._chunker()
        src = "def foo(): pass\n"
        chunks = chunker.chunk_file("my/module.py", src)
        for c in chunks:
            assert c.file_path == "my/module.py"

    def test_chunk_has_line_numbers(self):
        chunker = self._chunker()
        src = textwrap.dedent("""\
            def foo():
                pass

            def bar():
                return 42
        """)
        chunks = chunker.chunk_file("mod.py", src)
        for c in chunks:
            assert c.start_line >= 1
            assert c.end_line >= c.start_line

    def test_chunk_invalid_syntax_fallback(self):
        chunker = self._chunker()
        src = "def broken(:\n    pass"
        chunks = chunker.chunk_file("bad.py", src)
        # Should fall back to sliding window — not raise
        assert isinstance(chunks, list)

    def test_chunk_empty_source(self):
        chunker = self._chunker()
        chunks = chunker.chunk_file("empty.py", "")
        assert chunks == []

    def test_chunk_imports_in_module_header(self):
        chunker = self._chunker()
        src = textwrap.dedent("""\
            import os
            from typing import Optional

            def foo(): pass
        """)
        chunks = chunker.chunk_file("mod.py", src)
        header_chunks = [c for c in chunks if c.chunk_type == "module_header"]
        if header_chunks:
            assert "import" in header_chunks[0].content

    def test_chunk_language_detected(self):
        chunker = self._chunker()
        src = "def f(): pass\n"
        chunks = chunker.chunk_file("script.py", src)
        for c in chunks:
            assert c.language == "python"

    def test_chunk_async_function(self):
        chunker = self._chunker()
        src = textwrap.dedent("""\
            async def fetch(url: str) -> bytes:
                pass
        """)
        chunks = chunker.chunk_file("fetch.py", src)
        assert len(chunks) >= 1


class TestASTChunkerGeneric:
    def _chunker(self):
        from rag.ast_chunker import ASTChunker
        from rag.rag_config import RAGSettings
        return ASTChunker(settings=RAGSettings())

    def test_chunk_javascript(self):
        chunker = self._chunker()
        src = textwrap.dedent("""\
            function greet(name) {
                return `Hello ${name}`;
            }

            const calculate = (a, b) => a + b;
        """)
        chunks = chunker.chunk_file("utils.js", src)
        assert len(chunks) >= 1
        for c in chunks:
            assert c.language == "javascript"

    def test_chunk_go(self):
        chunker = self._chunker()
        src = textwrap.dedent("""\
            package main

            func Add(a, b int) int {
                return a + b
            }

            func main() {
                fmt.Println(Add(1, 2))
            }
        """)
        chunks = chunker.chunk_file("main.go", src)
        assert isinstance(chunks, list)
        for c in chunks:
            assert c.language == "go"

    def test_chunk_markdown_sliding(self):
        chunker = self._chunker()
        src = "# Title\n\nSome content.\n" * 10
        chunks = chunker.chunk_file("README.md", src)
        assert isinstance(chunks, list)

    def test_chunk_files_multiple(self):
        chunker = self._chunker()
        files = [
            {"file_path": "a.py", "content": "def a(): pass\n"},
            {"file_path": "b.py", "content": "def b(): pass\n"},
        ]
        chunks = chunker.chunk_files(files)
        assert len(chunks) >= 2


# ── CodeChunk ────────────────────────────────────────────────────────────


class TestCodeChunk:
    def test_to_metadata(self):
        from rag.ast_chunker import CodeChunk
        chunk = CodeChunk(
            content="def foo(): pass",
            file_path="utils.py",
            start_line=10,
            end_line=10,
            chunk_type="function",
            symbol_name="foo",
            language="python",
        )
        meta = chunk.to_metadata()
        assert meta["source_path"] == "utils.py"
        assert meta["start_line"] == 10
        assert meta["chunk_type"] == "function"
        assert meta["symbol_name"] == "foo"
        assert meta["language"] == "python"


# ── BM25Index ────────────────────────────────────────────────────────────


class TestBM25Index:
    def test_tokenizer(self):
        from rag.hybrid_retriever import BM25Index
        tokens = BM25Index._tokenize("getUserById(userId)")
        assert isinstance(tokens, list)
        assert len(tokens) > 0

    def test_tokenize_camel_case(self):
        from rag.hybrid_retriever import BM25Index
        tokens = BM25Index._tokenize("getUserById")
        joined = " ".join(tokens)
        assert "user" in joined.lower() or "get" in joined.lower()

    def test_build_and_search_without_library(self):
        from rag.hybrid_retriever import BM25Index
        from rag.ast_chunker import CodeChunk
        idx = BM25Index()
        # If rank_bm25 is not installed, build/search should not raise
        chunks = [
            CodeChunk(content="def authenticate(user): pass", file_path="auth.py"),
            CodeChunk(content="def hash_password(pwd): pass", file_path="auth.py"),
        ]
        idx.build(chunks)  # should not raise regardless
        results = idx.search("authentication user login")
        assert isinstance(results, list)


# ── RRF scoring ──────────────────────────────────────────────────────────


class TestRRFScore:
    def test_rrf_score_rank1(self):
        from rag.hybrid_retriever import _rrf_score
        score = _rrf_score(1, k=60)
        assert abs(score - 1 / 61) < 1e-9

    def test_rrf_score_rank10(self):
        from rag.hybrid_retriever import _rrf_score
        score = _rrf_score(10, k=60)
        assert abs(score - 1 / 70) < 1e-9

    def test_higher_rank_lower_score(self):
        from rag.hybrid_retriever import _rrf_score
        assert _rrf_score(1) > _rrf_score(5) > _rrf_score(10)


# ── HybridRetriever ──────────────────────────────────────────────────────


class TestHybridRetriever:
    def _make_retriever(self):
        from rag.hybrid_retriever import HybridRetriever
        from rag.rag_config import RAGSettings

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 384
        mock_embeddings.embed_documents.return_value = [[0.1] * 384]

        cfg = RAGSettings(RAG_RETRIEVAL_MODE="hybrid", RAG_TOP_K=5, RAG_FINAL_K=3)
        retriever = HybridRetriever(mock_embeddings, settings=cfg)
        return retriever

    def test_init(self):
        retriever = self._make_retriever()
        assert retriever.is_built is False

    def test_retrieve_before_build_returns_empty(self):
        retriever = self._make_retriever()
        results = retriever.retrieve("test query")
        assert results == []

    def test_retrieve_as_context_empty(self):
        retriever = self._make_retriever()
        ctx = retriever.retrieve_as_context("query")
        assert ctx == ""

    def test_rrf_fusion_with_mocked_indexes(self):
        from rag.hybrid_retriever import HybridRetriever, RetrievedChunk
        from rag.ast_chunker import CodeChunk
        from rag.rag_config import RAGSettings

        mock_embeddings = MagicMock()
        cfg = RAGSettings(RAG_RETRIEVAL_MODE="hybrid", RAG_FINAL_K=2, RAG_TOP_K=3, RAG_RRF_K=60)
        retriever = HybridRetriever(mock_embeddings, settings=cfg)
        retriever._is_built = True

        chunk_a = CodeChunk(content="def authenticate(u): pass", file_path="auth.py", start_line=1)
        chunk_b = CodeChunk(content="def hash_pw(pw): pass", file_path="auth.py", start_line=10)

        # Mock both sub-indexes
        retriever._dense.search = MagicMock(return_value=[
            (chunk_a, 0.9),
            (chunk_b, 0.7),
        ])
        retriever._bm25.search = MagicMock(return_value=[(0, 5.0), (1, 3.0)])
        retriever._chunks = [chunk_a, chunk_b]

        results = retriever.retrieve("authentication password")
        assert len(results) <= 2
        for r in results:
            assert isinstance(r, RetrievedChunk)
            assert r.rrf_score > 0


# ── HistoryIndexer ───────────────────────────────────────────────────────


class TestHistoryIndexer:
    def _make_indexer(self, tmp_dir: str):
        from rag.history_indexer import HistoryIndexer
        from rag.rag_config import RAGSettings

        mock_embeddings = MagicMock()

        cfg = RAGSettings(
            RAG_HISTORY_PATH=os.path.join(tmp_dir, "history.jsonl"),
            RAG_HISTORY_MAX_ENTRIES=10,
        )

        with patch("rag.history_indexer.FAISS", create=True):
            indexer = HistoryIndexer(mock_embeddings, settings=cfg)

        return indexer

    def test_add_review_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            from rag.history_indexer import HistoryIndexer
            from rag.rag_config import RAGSettings

            mock_embeddings = MagicMock()
            path = os.path.join(tmp, "history.jsonl")
            cfg = RAGSettings(RAG_HISTORY_PATH=path, RAG_HISTORY_MAX_ENTRIES=10)
            indexer = HistoryIndexer(mock_embeddings, settings=cfg)
            # Disable FAISS by mocking _rebuild_index
            indexer._rebuild_index = MagicMock()

            entry = indexer.add_review(
                pr_number=42,
                repo="owner/repo",
                title="Fix auth bug",
                diff_summary="Removed SQL injection vector",
                findings=[{"severity": "error", "message": "SQL injection"}],
            )

            assert entry["pr_number"] == 42
            assert entry["repo"] == "owner/repo"
            assert os.path.exists(path)

            # Read back
            with open(path) as f:
                lines = [l for l in f if l.strip()]
            assert len(lines) == 1
            saved = json.loads(lines[0])
            assert saved["pr_number"] == 42

    def test_load_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            from rag.history_indexer import HistoryIndexer
            from rag.rag_config import RAGSettings

            path = os.path.join(tmp, "history.jsonl")
            # Pre-populate
            entry = {
                "pr_number": 7,
                "repo": "foo/bar",
                "timestamp": "2024-01-01T00:00:00+00:00",
                "title": "Refactor auth",
                "diff_summary": "Big refactor",
                "findings": [],
                "reviewer_comments": [],
                "resolution": "merged",
                "embedding_text": "PR: Refactor auth\nSummary: Big refactor",
                "metadata": {},
            }
            with open(path, "w") as f:
                f.write(json.dumps(entry) + "\n")

            mock_embeddings = MagicMock()
            cfg = RAGSettings(RAG_HISTORY_PATH=path, RAG_HISTORY_MAX_ENTRIES=10)
            indexer = HistoryIndexer(mock_embeddings, settings=cfg)
            indexer._rebuild_index = MagicMock()

            count = indexer.load()
            assert count == 1
            assert indexer.entry_count == 1

    def test_update_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            from rag.history_indexer import HistoryIndexer
            from rag.rag_config import RAGSettings

            path = os.path.join(tmp, "history.jsonl")
            mock_embeddings = MagicMock()
            cfg = RAGSettings(RAG_HISTORY_PATH=path, RAG_HISTORY_MAX_ENTRIES=10)
            indexer = HistoryIndexer(mock_embeddings, settings=cfg)
            indexer._rebuild_index = MagicMock()

            indexer.add_review(1, "a/b", "PR 1", "summary", [], resolution="open")
            updated = indexer.update_resolution(1, "a/b", "merged")
            assert updated is True
            assert indexer._entries[0]["resolution"] == "merged"

    def test_update_resolution_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            from rag.history_indexer import HistoryIndexer
            from rag.rag_config import RAGSettings

            mock_embeddings = MagicMock()
            cfg = RAGSettings(
                RAG_HISTORY_PATH=os.path.join(tmp, "h.jsonl"),
                RAG_HISTORY_MAX_ENTRIES=10,
            )
            indexer = HistoryIndexer(mock_embeddings, settings=cfg)
            indexer._rebuild_index = MagicMock()

            result = indexer.update_resolution(999, "no/repo", "merged")
            assert result is False

    def test_max_entries_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            from rag.history_indexer import HistoryIndexer
            from rag.rag_config import RAGSettings

            path = os.path.join(tmp, "history.jsonl")
            mock_embeddings = MagicMock()
            cfg = RAGSettings(RAG_HISTORY_PATH=path, RAG_HISTORY_MAX_ENTRIES=3)
            indexer = HistoryIndexer(mock_embeddings, settings=cfg)
            indexer._rebuild_index = MagicMock()

            for i in range(5):
                indexer.add_review(i, f"o/r{i}", f"PR {i}", "sum", [])

            assert indexer.entry_count <= 3

    def test_find_similar_no_index_returns_recent(self):
        with tempfile.TemporaryDirectory() as tmp:
            from rag.history_indexer import HistoryIndexer
            from rag.rag_config import RAGSettings

            path = os.path.join(tmp, "history.jsonl")
            mock_embeddings = MagicMock()
            cfg = RAGSettings(RAG_HISTORY_PATH=path, RAG_HISTORY_MAX_ENTRIES=10)
            indexer = HistoryIndexer(mock_embeddings, settings=cfg)
            indexer._rebuild_index = MagicMock()  # prevents FAISS build

            for i in range(4):
                indexer.add_review(i, "a/b", f"PR {i}", "sum", [])

            indexer._vectorstore = None  # no index
            results = indexer.find_similar("authentication", k=2)
            assert len(results) <= 2

    def test_format_for_prompt_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            from rag.history_indexer import HistoryIndexer
            from rag.rag_config import RAGSettings

            mock_embeddings = MagicMock()
            cfg = RAGSettings(
                RAG_HISTORY_PATH=os.path.join(tmp, "h.jsonl"),
                RAG_HISTORY_MAX_ENTRIES=10,
            )
            indexer = HistoryIndexer(mock_embeddings, settings=cfg)
            indexer._rebuild_index = MagicMock()
            result = indexer.format_for_prompt("something")
            assert result == ""

    def test_embedding_text_built(self):
        with tempfile.TemporaryDirectory() as tmp:
            from rag.history_indexer import HistoryIndexer, _make_entry
            from rag.rag_config import RAGSettings

            entry = _make_entry(
                pr_number=10,
                repo="x/y",
                title="Security fix",
                diff_summary="Patched XSS",
                findings=[{"severity": "error", "message": "XSS vulnerability detected"}],
            )
            assert "Security fix" in entry["embedding_text"]
            assert "Patched XSS" in entry["embedding_text"]
