import os
import pathlib
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from core.config import get_settings
from core.logger import get_logger

logger = get_logger("rag.indexer")


def _get_embeddings():
    """Return an embedding model based on the configured LLM provider."""
    settings = get_settings()
    provider = settings.LLM_PROVIDER

    if provider == "openai" and settings.OPENAI_API_KEY:
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model="text-embedding-3-small")

    if provider == "gemini" and settings.GEMINI_API_KEY:
        from langchain_community.embeddings import HuggingFaceEmbeddings
        logger.info("Using local HuggingFace embeddings (Gemini has no embeddings API in langchain)")
        return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    # Default fallback: free local embeddings via HuggingFace
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
        logger.info("Using local HuggingFace embeddings (all-MiniLM-L6-v2)")
        return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    except ImportError:
        raise RuntimeError(
            "No embedding model available. Install sentence-transformers: pip install sentence-transformers"
        )


class CodebaseIndexer:
    def __init__(self, codebase_path: str = None, index_path: str = None):
        settings = get_settings()
        self.codebase_path = codebase_path or settings.CODEBASE_PATH
        self.index_path = index_path or settings.FAISS_INDEX_PATH
        self.stats = {"files_indexed": 0, "chunks_created": 0}

    def _load_files(self) -> list[dict]:
        docs = []
        valid_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".md"}
        skip_dirs = {"node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build"}

        for root, dirs, files in os.walk(self.codebase_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for file in files:
                ext = os.path.splitext(file)[1]
                if ext in valid_exts:
                    file_path = os.path.join(root, file)
                    try:
                        if os.path.getsize(file_path) > 100 * 1024:
                            continue
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        docs.append({"content": content, "source_path": file_path})
                    except (FileNotFoundError, UnicodeDecodeError):
                        continue
        return docs

    def _split_documents(self, docs: list[dict]) -> list:
        splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=80)
        chunks = []
        for doc in docs:
            doc_chunks = splitter.create_documents(
                [doc["content"]],
                metadatas=[{"source_path": doc["source_path"]}]
            )
            chunks.extend(doc_chunks)
        return chunks

    def build_index(self) -> None:
        docs = self._load_files()
        self.stats["files_indexed"] = len(docs)
        chunks = self._split_documents(docs)
        self.stats["chunks_created"] = len(chunks)

        print(f"Loaded {self.stats['files_indexed']} files.")
        print(f"Created {self.stats['chunks_created']} chunks.")

        embeddings = _get_embeddings()
        vectorstore = FAISS.from_documents(chunks, embeddings)
        vectorstore.save_local(self.index_path)
        print("FAISS index saved successfully.")

    def get_stats(self) -> dict:
        return self.stats
