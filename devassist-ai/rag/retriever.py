import os
from langchain_community.vectorstores import FAISS
from core.config import get_settings
from core.logger import get_logger

logger = get_logger("rag.retriever")


def _get_embeddings():
    """Return the same embedding model used by the indexer."""
    from rag.indexer import _get_embeddings as get_embed
    return get_embed()


class CodebaseRetriever:
    def __init__(self, index_path: str = None):
        settings = get_settings()
        self.index_path = index_path or settings.FAISS_INDEX_PATH
        self.vectorstore = None

    def load_index(self) -> None:
        if not os.path.exists(self.index_path):
            raise FileNotFoundError("FAISS index not found. Run scripts/setup_index.py first.")
        try:
            embeddings = _get_embeddings()
            self.vectorstore = FAISS.load_local(
                self.index_path,
                embeddings,
                allow_dangerous_deserialization=True
            )
        except Exception as e:
            raise RuntimeError(f"FAISS index may be corrupted. Please re-run scripts/setup_index.py. Error: {e}")

    def get_context(self, query: str, k: int = 5) -> str:
        if self.vectorstore is None:
            self.load_index()

        results = self.vectorstore.similarity_search(query, k=k)
        formatted_results = []
        for res in results:
            source = res.metadata.get("source_path", "Unknown")
            formatted_results.append(f"--- File: {source} ---\n{res.page_content}")

        return "\n\n".join(formatted_results)

    def is_loaded(self) -> bool:
        return self.vectorstore is not None
