"""
Centralized embedding model factory for Phase 4 RAG.

Provides a single place to get embedding models, avoiding the duplicated
_get_embeddings() functions scattered across rag/indexer.py and rag/retriever.py.
Supports HuggingFace (local, free), OpenAI, and Gemini providers.
"""

from __future__ import annotations

from typing import Any, Optional

from core.logger import get_logger
from rag.rag_config import RAGSettings

logger = get_logger("rag.embeddings")

_cached_embedding_model = None


def get_embedding_model(settings: Optional[RAGSettings] = None) -> Any:
    """Return an initialized embedding model based on RAGSettings.

    Priority:
        1. HuggingFace local (default — free, no API key needed)
        2. OpenAI text-embedding-3-small (if provider='openai')
        3. Fallback: all-MiniLM-L6-v2 via sentence-transformers directly

    Args:
        settings: Optional :class:`~rag.rag_config.RAGSettings` instance.
            Uses singleton if not provided.

    Returns:
        An embedding object with an ``embed_documents(texts)`` and
        ``embed_query(text)`` interface (LangChain-compatible).

    Raises:
        RuntimeError: If no embedding model can be loaded.
    """
    global _cached_embedding_model
    if _cached_embedding_model is not None:
        return _cached_embedding_model

    from rag.rag_config import get_rag_settings
    cfg = settings or get_rag_settings()
    provider = cfg.RAG_EMBEDDING_PROVIDER.lower()
    model_name = cfg.RAG_EMBEDDING_MODEL

    if provider == "openai":
        _cached_embedding_model = _load_openai_embeddings(model_name)
        return _cached_embedding_model
    if provider == "huggingface":
        _cached_embedding_model = _load_huggingface_embeddings(model_name)
        return _cached_embedding_model

    # Auto-select based on what's installed
    try:
        _cached_embedding_model = _load_huggingface_embeddings(model_name)
        return _cached_embedding_model
    except ImportError:
        pass

    raise RuntimeError(
        "No embedding backend available. "
        "Install sentence-transformers: pip install sentence-transformers"
    )


def get_embedding_dimension(settings: Optional[RAGSettings] = None) -> int:
    """Return the embedding vector dimension for the configured model.

    Used to pre-allocate FAISS/LanceDB index structures.

    Args:
        settings: Optional RAGSettings instance.

    Returns:
        Integer embedding dimension (e.g. 384 for all-MiniLM-L6-v2).
    """
    from rag.rag_config import get_rag_settings
    cfg = settings or get_rag_settings()
    model_name = cfg.RAG_EMBEDDING_MODEL

    # Known dimensions — avoids loading the model just for this
    _KNOWN_DIMS: dict[str, int] = {
        "all-MiniLM-L6-v2": 384,
        "all-MiniLM-L12-v2": 384,
        "all-mpnet-base-v2": 768,
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
        "bge-small-en-v1.5": 384,
        "bge-base-en-v1.5": 768,
    }

    for key, dim in _KNOWN_DIMS.items():
        if key in model_name:
            return dim

    # Fallback: load model and probe dimension
    logger.info("Probing embedding dimension for unknown model: %s", model_name)
    model = get_embedding_model(cfg)
    probe = model.embed_query("dimension probe")
    return len(probe)


# ── Private loaders ────────────────────────────────────────────────────


def _load_huggingface_embeddings(model_name: str) -> Any:
    """Load a HuggingFace sentence-transformer embedding model.

    Args:
        model_name: HuggingFace model identifier.

    Returns:
        LangChain-compatible HuggingFaceEmbeddings instance.

    Raises:
        ImportError: If sentence-transformers is not installed.
    """
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
        logger.info("Loading HuggingFace embeddings: %s", model_name)
        # Use cached model — suppress the 8 HuggingFace HTTP HEAD/GET calls on every startup
        import os as _os
        _os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        _os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
        return HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": "cpu"},  # explicit; avoids CUDA probe on CPU-only machines
            encode_kwargs={"normalize_embeddings": True},
        )
    except ImportError:
        # Try direct sentence-transformers as fallback
        from sentence_transformers import SentenceTransformer

        class _STWrapper:
            """Thin LangChain-compatible wrapper around SentenceTransformer."""

            def __init__(self, m: SentenceTransformer) -> None:
                self._model = m

            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                return self._model.encode(texts, convert_to_numpy=True).tolist()

            def embed_query(self, text: str) -> list[float]:
                return self._model.encode([text], convert_to_numpy=True)[0].tolist()

        logger.info("Using direct SentenceTransformer: %s", model_name)
        return _STWrapper(SentenceTransformer(model_name))


def _load_openai_embeddings(model_name: str) -> Any:
    """Load OpenAI embeddings.

    Args:
        model_name: OpenAI embedding model, e.g. 'text-embedding-3-small'.

    Returns:
        LangChain-compatible OpenAIEmbeddings instance.

    Raises:
        ImportError: If langchain-openai is not installed.
    """
    from langchain_openai import OpenAIEmbeddings
    logger.info("Loading OpenAI embeddings: %s", model_name)
    return OpenAIEmbeddings(model=model_name)
