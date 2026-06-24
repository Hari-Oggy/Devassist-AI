"""
RAG Phase 4 Configuration — Advanced hybrid retrieval settings.

Separate from core/config.py to avoid modifying existing settings.
Reads from the same .env file via pydantic_settings.
"""

from __future__ import annotations

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class RAGSettings(BaseSettings):
    """Phase 4 RAG configuration — hybrid search + AST-aware chunking.

    All fields are optional with sensible defaults so the system
    degrades gracefully when not configured.
    """

    # ── Embedding Model ──────────────────────────────────────────────────
    RAG_EMBEDDING_MODEL: str = Field(
        default="all-MiniLM-L6-v2",
        description="HuggingFace sentence-transformer model for embeddings",
    )
    RAG_EMBEDDING_PROVIDER: str = Field(
        default="huggingface",
        description="Embedding provider: 'huggingface' | 'openai' | 'gemini'",
    )

    # ── Chunking Strategy ────────────────────────────────────────────────
    RAG_CHUNK_STRATEGY: str = Field(
        default="ast",
        description="Chunking strategy: 'ast' (smart) | 'sliding' (legacy fixed-size)",
    )
    RAG_CHUNK_SIZE: int = Field(
        default=600,
        description="Max characters per chunk (for sliding window fallback)",
    )
    RAG_CHUNK_OVERLAP: int = Field(
        default=80,
        description="Overlap between chunks in sliding window mode",
    )
    RAG_AST_MAX_CHUNK_LINES: int = Field(
        default=80,
        description="Max lines for a single AST-aware code chunk",
    )

    # ── Hybrid Search ────────────────────────────────────────────────────
    RAG_RETRIEVAL_MODE: str = Field(
        default="hybrid",
        description="Retrieval mode: 'dense' | 'bm25' | 'hybrid'",
    )
    RAG_TOP_K: int = Field(
        default=10,
        description="Number of candidates per retrieval pass (before reranking)",
    )
    RAG_FINAL_K: int = Field(
        default=5,
        description="Final number of chunks to include in context after reranking",
    )
    RAG_HYBRID_ALPHA: float = Field(
        default=0.6,
        description="Weight for dense score in hybrid fusion (0.0=BM25-only, 1.0=dense-only)",
    )
    RAG_RRF_K: int = Field(
        default=60,
        description="Reciprocal Rank Fusion constant k (higher = smoother ranking)",
    )

    # ── Storage ──────────────────────────────────────────────────────────
    RAG_INDEX_DIR: str = Field(
        default="./data/rag_v2",
        description="Directory for Phase 4 index files (separate from legacy FAISS)",
    )
    RAG_HISTORY_PATH: str = Field(
        default="./data/review_history.jsonl",
        description="Path to the JSONL review history file for project memory",
    )
    RAG_HISTORY_MAX_ENTRIES: int = Field(
        default=500,
        description="Maximum number of review history entries to retain",
    )

    # ── Code-Specific ────────────────────────────────────────────────────
    RAG_CODE_EXTENSIONS: str = Field(
        default=".py,.js,.ts,.jsx,.tsx,.java,.go,.rs,.c,.cpp,.h,.hpp,.md",
        description="Comma-separated file extensions to index",
    )
    RAG_MAX_FILE_BYTES: int = Field(
        default=512_000,
        description="Skip files larger than this (bytes)",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def code_extensions(self) -> set[str]:
        """Return code extensions as a Python set."""
        return {ext.strip() for ext in self.RAG_CODE_EXTENSIONS.split(",")}

    @property
    def is_hybrid(self) -> bool:
        """Return True when hybrid retrieval is enabled."""
        return self.RAG_RETRIEVAL_MODE == "hybrid"


# Singleton
_rag_settings: RAGSettings | None = None


def get_rag_settings() -> RAGSettings:
    """Return a singleton RAGSettings instance."""
    global _rag_settings
    if _rag_settings is None:
        _rag_settings = RAGSettings()
    return _rag_settings
