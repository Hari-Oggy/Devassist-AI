"""
Hybrid Retriever — Phase 4 RAG component.

Combines dense vector search (embedding similarity) with sparse BM25 keyword
search using Reciprocal Rank Fusion (RRF) to produce a single ranked list.

Why hybrid?
    - Dense search: great for semantic similarity ("functions that validate input")
    - BM25: great for exact token matches (function names, error codes, CVE IDs)
    - RRF fusion: rank-based combination — robust, no score normalization needed

Architecture:
    HybridRetriever
        ├── DenseIndex       (FAISS — stored in data/rag_v2/dense.faiss)
        ├── BM25Index        (rank_bm25 — stored in data/rag_v2/bm25.pkl)
        └── RRF Fusion       (Reciprocal Rank Fusion)

The retriever works with CodeChunk objects from rag/ast_chunker.py and
stores metadata alongside the vector index for rich context injection.
"""

from __future__ import annotations

import os
import pickle
from dataclasses import dataclass, field
from typing import Any, Optional

from core.logger import get_logger
from rag.ast_chunker import CodeChunk
from rag.rag_config import RAGSettings, get_rag_settings

logger = get_logger("rag.hybrid_retriever")


# ── Retrieved result dataclass ─────────────────────────────────────────


@dataclass
class RetrievedChunk:
    """A code chunk returned by the retriever, with relevance scores.

    Attributes:
        chunk: The original :class:`~rag.ast_chunker.CodeChunk`.
        dense_rank: Rank in the dense retrieval pass (1-indexed, lower = better).
        bm25_rank: Rank in the BM25 retrieval pass.
        rrf_score: Fused Reciprocal Rank Fusion score (higher = better).
    """

    chunk: CodeChunk
    dense_rank: int = 0
    bm25_rank: int = 0
    rrf_score: float = 0.0


# ── BM25 index wrapper ─────────────────────────────────────────────────


class BM25Index:
    """Sparse BM25 keyword index over code chunks.

    Uses the ``rank_bm25`` library (pip install rank-bm25). Falls back
    gracefully to returning an empty result list if not installed.
    """

    def __init__(self) -> None:
        self._bm25 = None
        self._chunks: list[CodeChunk] = []
        self._available = self._check_available()

    @staticmethod
    def _check_available() -> bool:
        try:
            import rank_bm25  # noqa: F401
            return True
        except ImportError:
            logger.warning(
                "rank-bm25 not installed — BM25 search disabled. "
                "Install with: pip install rank-bm25"
            )
            return False

    def build(self, chunks: list[CodeChunk]) -> None:
        """Build the BM25 index from a list of CodeChunks.

        Args:
            chunks: All code chunks to index.
        """
        if not self._available:
            return
        from rank_bm25 import BM25Okapi
        self._chunks = chunks
        tokenized = [self._tokenize(c.content) for c in chunks]
        self._bm25 = BM25Okapi(tokenized)
        logger.info("BM25 index built: %d chunks", len(chunks))

    def search(self, query: str, k: int = 10) -> list[tuple[int, float]]:
        """Search the BM25 index.

        Args:
            query: Natural language or code query.
            k: Number of top results to return.

        Returns:
            List of (chunk_index, bm25_score) tuples sorted descending.
        """
        if not self._bm25 or not self._chunks:
            return []
        tokens = self._tokenize(query)
        scores = self._bm25.get_scores(tokens)
        top_k = sorted(enumerate(scores), key=lambda x: -x[1])[:k]
        return [(idx, float(score)) for idx, score in top_k if score > 0]

    def save(self, path: str) -> None:
        """Serialize the BM25 index to a pickle file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"bm25": self._bm25, "chunks": self._chunks}, f)
        logger.info("BM25 index saved: %s", path)

    def load(self, path: str) -> bool:
        """Deserialize a BM25 index from a pickle file.

        Returns:
            True on success, False if file does not exist.
        """
        if not os.path.exists(path):
            return False
        with open(path, "rb") as f:
            data = pickle.load(f)
        self._bm25 = data.get("bm25")
        self._chunks = data.get("chunks", [])
        logger.info("BM25 index loaded: %d chunks from %s", len(self._chunks), path)
        return True

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple whitespace + camelCase tokenizer for code."""
        # Split on non-alphanumeric characters
        tokens = re.split(r"[^a-zA-Z0-9_]", text)
        # Also split camelCase: myFunction → ['my', 'Function']
        expanded: list[str] = []
        for tok in tokens:
            if tok:
                sub = re.sub(r"([a-z])([A-Z])", r"\1 \2", tok).split()
                expanded.extend(s.lower() for s in sub if len(s) > 1)
        return expanded


import re  # noqa: E402 — needed after BM25Index definition


# ── Dense FAISS index wrapper ──────────────────────────────────────────


class DenseIndex:
    """Dense vector index backed by FAISS.

    Wraps FAISS + LangChain to store and retrieve CodeChunks by semantic
    embedding similarity.
    """

    def __init__(self, embedding_model: Any) -> None:
        self._embeddings = embedding_model
        self._vectorstore = None
        self._chunks: list[CodeChunk] = []

    def build(self, chunks: list[CodeChunk]) -> None:
        """Build the FAISS index from CodeChunks.

        Args:
            chunks: All code chunks to embed and index.
        """
        if not chunks:
            logger.warning("DenseIndex.build called with empty chunk list")
            return

        try:
            from langchain_community.vectorstores import FAISS
            from langchain.schema import Document
        except ImportError:
            logger.error(
                "langchain-community not installed. "
                "Install with: pip install langchain-community"
            )
            return

        self._chunks = chunks
        docs = [
            Document(
                page_content=chunk.content,
                metadata=chunk.to_metadata(),
            )
            for chunk in chunks
        ]

        logger.info("Building dense index for %d chunks...", len(docs))
        self._vectorstore = FAISS.from_documents(docs, self._embeddings)
        logger.info("Dense FAISS index built.")

    def search(self, query: str, k: int = 10) -> list[tuple[CodeChunk, float]]:
        """Search the dense index.

        Args:
            query: Query string to embed.
            k: Number of top results to return.

        Returns:
            List of (CodeChunk, similarity_score) tuples.
        """
        if self._vectorstore is None:
            return []

        try:
            results = self._vectorstore.similarity_search_with_score(query, k=k)
            hits: list[tuple[CodeChunk, float]] = []
            for doc, score in results:
                # Reconstruct a CodeChunk from stored metadata
                meta = doc.metadata
                chunk = CodeChunk(
                    content=doc.page_content,
                    file_path=meta.get("source_path", ""),
                    start_line=meta.get("start_line", 0),
                    end_line=meta.get("end_line", 0),
                    chunk_type=meta.get("chunk_type", "block"),
                    symbol_name=meta.get("symbol_name", ""),
                    language=meta.get("language", "unknown"),
                )
                hits.append((chunk, float(score)))
            return hits
        except Exception as exc:
            logger.error("Dense search error: %s", exc)
            return []

    def save(self, path: str) -> None:
        """Save the FAISS index to disk."""
        if self._vectorstore is None:
            return
        os.makedirs(path, exist_ok=True)
        self._vectorstore.save_local(path)
        logger.info("Dense index saved: %s", path)

    def load(self, path: str) -> bool:
        """Load a FAISS index from disk.

        Returns:
            True on success, False if path does not exist.
        """
        if not os.path.exists(path):
            return False
        try:
            from langchain_community.vectorstores import FAISS
            self._vectorstore = FAISS.load_local(
                path,
                self._embeddings,
                allow_dangerous_deserialization=True,
            )
            logger.info("Dense index loaded from: %s", path)
            return True
        except Exception as exc:
            logger.error("Failed to load dense index: %s", exc)
            return False


# ── RRF fusion ─────────────────────────────────────────────────────────


def _rrf_score(rank: int, k: int = 60) -> float:
    """Compute Reciprocal Rank Fusion score.

    Args:
        rank: 1-indexed rank (lower = better candidate).
        k: Smoothing constant (default 60 from the original RRF paper).

    Returns:
        RRF score: ``1 / (k + rank)``.
    """
    return 1.0 / (k + rank)


# ── Main HybridRetriever ────────────────────────────────────────────────


class HybridRetriever:
    """Hybrid retriever combining dense (FAISS) and sparse (BM25) search.

    Uses Reciprocal Rank Fusion (RRF) to merge rankings from both systems
    into a single, high-quality ranked list.

    Example::

        from rag.embeddings import get_embedding_model
        embeddings = get_embedding_model()

        retriever = HybridRetriever(embeddings)
        retriever.build(chunks)  # list[CodeChunk]

        results = retriever.retrieve("how is authentication handled?", k=5)
        for r in results:
            print(r.chunk.file_path, r.chunk.symbol_name, r.rrf_score)
    """

    def __init__(
        self,
        embedding_model: Any,
        settings: Optional[RAGSettings] = None,
    ) -> None:
        self._cfg = settings or get_rag_settings()
        self._dense = DenseIndex(embedding_model)
        self._bm25 = BM25Index()
        self._chunks: list[CodeChunk] = []
        self._is_built = False

    # ── Public API ─────────────────────────────────────────────────────

    def build(self, chunks: list[CodeChunk]) -> None:
        """Build both dense and BM25 indexes from code chunks.

        Args:
            chunks: List of :class:`~rag.ast_chunker.CodeChunk` to index.
        """
        self._chunks = chunks
        self._dense.build(chunks)
        self._bm25.build(chunks)
        self._is_built = True
        logger.info(
            "HybridRetriever built: %d chunks (dense + BM25)", len(chunks)
        )

    def retrieve(self, query: str, k: Optional[int] = None) -> list[RetrievedChunk]:
        """Retrieve top-k chunks using hybrid RRF fusion.

        Args:
            query: The search query (natural language or code snippet).
            k: Number of results to return. Uses ``RAG_FINAL_K`` if not set.

        Returns:
            List of :class:`RetrievedChunk` sorted by RRF score (descending).
        """
        if not self._is_built:
            logger.warning("HybridRetriever: retrieve() called before build()")
            return []

        final_k = k or self._cfg.RAG_FINAL_K
        top_k = self._cfg.RAG_TOP_K
        mode = self._cfg.RAG_RETRIEVAL_MODE.lower()
        rrf_k = self._cfg.RAG_RRF_K

        dense_hits = []
        bm25_hits = []

        if mode in ("dense", "hybrid"):
            dense_hits = self._dense.search(query, k=top_k)

        if mode in ("bm25", "hybrid"):
            bm25_raw = self._bm25.search(query, k=top_k)
            # Map chunk index → chunk
            bm25_hits = [
                (self._chunks[idx], score)
                for idx, score in bm25_raw
                if idx < len(self._chunks)
            ]

        if mode == "dense":
            return self._wrap_results(dense_hits, [], rrf_k, final_k)
        if mode == "bm25":
            return self._wrap_results([], bm25_hits, rrf_k, final_k)
        return self._wrap_results(dense_hits, bm25_hits, rrf_k, final_k)

    def retrieve_as_context(self, query: str, k: Optional[int] = None) -> str:
        """Retrieve and format results as a plain-text context string.

        Suitable for injection directly into an LLM prompt.

        Args:
            query: Search query.
            k: Number of chunks to include.

        Returns:
            Formatted string with file path, symbol, and code content.
        """
        results = self.retrieve(query, k=k)
        parts = []
        for r in results:
            c = r.chunk
            header = f"--- {c.file_path}"
            if c.symbol_name:
                header += f" [{c.symbol_name}]"
            header += f" (lines {c.start_line}–{c.end_line}) ---"
            parts.append(f"{header}\n{c.content}")
        return "\n\n".join(parts)

    def save(self, index_dir: str) -> None:
        """Persist both indexes to disk.

        Args:
            index_dir: Directory to save dense/ and bm25.pkl into.
        """
        dense_path = os.path.join(index_dir, "dense")
        bm25_path = os.path.join(index_dir, "bm25.pkl")
        self._dense.save(dense_path)
        self._bm25.save(bm25_path)
        logger.info("HybridRetriever saved to: %s", index_dir)

    def load(self, index_dir: str) -> bool:
        """Load both indexes from disk.

        Args:
            index_dir: Directory containing dense/ and bm25.pkl.

        Returns:
            True if at least the dense index loaded successfully.
        """
        dense_path = os.path.join(index_dir, "dense")
        bm25_path = os.path.join(index_dir, "bm25.pkl")

        dense_ok = self._dense.load(dense_path)
        bm25_ok = self._bm25.load(bm25_path)
        self._is_built = dense_ok

        # Sync chunk list from BM25 for RRF
        if bm25_ok:
            self._chunks = self._bm25._chunks

        logger.info(
            "HybridRetriever load: dense=%s bm25=%s", dense_ok, bm25_ok
        )
        return dense_ok

    @property
    def is_built(self) -> bool:
        """Return True if the retriever is ready to serve queries."""
        return self._is_built

    # ── Private helpers ────────────────────────────────────────────────

    def _wrap_results(
        self,
        dense_hits: list[tuple[CodeChunk, float]],
        bm25_hits: list[tuple[CodeChunk, float]],
        rrf_k: int,
        final_k: int,
    ) -> list[RetrievedChunk]:
        """Fuse dense and BM25 results with RRF."""
        # Build RRF score accumulator keyed by (file_path, start_line)
        scores: dict[tuple, RetrievedChunk] = {}

        def _key(chunk: CodeChunk) -> tuple:
            return (chunk.file_path, chunk.start_line)

        # Dense ranks
        for rank, (chunk, _score) in enumerate(dense_hits, start=1):
            k = _key(chunk)
            if k not in scores:
                scores[k] = RetrievedChunk(chunk=chunk, dense_rank=rank)
            else:
                scores[k].dense_rank = rank
            scores[k].rrf_score += _rrf_score(rank, rrf_k)

        # BM25 ranks
        for rank, (chunk, _score) in enumerate(bm25_hits, start=1):
            k = _key(chunk)
            if k not in scores:
                scores[k] = RetrievedChunk(chunk=chunk, bm25_rank=rank)
            else:
                scores[k].bm25_rank = rank
            scores[k].rrf_score += _rrf_score(rank, rrf_k)

        # Sort by RRF score descending
        ranked = sorted(scores.values(), key=lambda r: r.rrf_score, reverse=True)
        return ranked[:final_k]
