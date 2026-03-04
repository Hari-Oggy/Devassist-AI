"""
Reranker for RAG pipeline.
Uses a cross-encoder model to rerank retrieved chunks by relevance.
"""

from core.logger import get_logger

logger = get_logger("rag.reranker")

try:
    from sentence_transformers import CrossEncoder
    HAS_CROSS_ENCODER = True
except ImportError:
    HAS_CROSS_ENCODER = False


class Reranker:
    """Reranks retrieved documents using a cross-encoder model for higher precision."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        if not HAS_CROSS_ENCODER:
            logger.warning("sentence-transformers not installed. Reranking disabled.")
            self.model = None
            return
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, documents: list[dict], top_k: int = 3) -> list[dict]:
        """
        Rerank documents by relevance to the query.

        Args:
            query: The search query.
            documents: List of dicts with at least 'content' and 'source_path'.
            top_k: Number of top results to return.

        Returns:
            Top-k documents sorted by relevance score.
        """
        if not self.model or not documents:
            return documents[:top_k]

        pairs = [(query, doc["content"]) for doc in documents]
        scores = self.model.predict(pairs)

        scored_docs = list(zip(documents, scores))
        scored_docs.sort(key=lambda x: x[1], reverse=True)

        return [doc for doc, score in scored_docs[:top_k]]
