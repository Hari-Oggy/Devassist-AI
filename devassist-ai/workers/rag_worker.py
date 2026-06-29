"""
workers/rag_worker.py
Celery task for asynchronously building and updating RAG indexes per repository.
"""

import asyncio
import os
from typing import Any

from sqlalchemy import update
from taskqueue.celery_app import celery_app
from core.config import get_settings
from core.logger import get_logger
from models.database import get_db_session_context
from models.repositories import RepositoryRepo
from models.entities import ProviderType, Repository
from codegraph.repo_cloner import RepoCloner
from rag.ast_chunker import ASTChunker
from rag.hybrid_retriever import HybridRetriever
from rag.embeddings import get_embedding_model
from rag.rag_config import get_rag_settings

logger = get_logger("workers.rag_worker")
settings = get_settings()


def _get_repo_clone_url(repo: Repository) -> str:
    """Constructs the correct clone URL for the repository with authentication."""
    provider = repo.provider
    project_path = repo.full_name

    if provider == ProviderType.GITLAB:
        gitlab_token = getattr(settings, "GITLAB_TOKEN", None) or ""
        gitlab_api_url = getattr(settings, "GITLAB_API_URL", None) or "https://gitlab.com"
        from urllib.parse import urlparse
        parsed = urlparse(gitlab_api_url)
        host = parsed.netloc or "gitlab.com"
        scheme = parsed.scheme or "https"
        if gitlab_token:
            return f"{scheme}://oauth2:{gitlab_token}@{host}/{project_path}.git"
        return f"{scheme}://{host}/{project_path}.git"
    else:
        # GitHub
        from agents.tools.github_tool import get_github_client
        try:
            github_client = get_github_client(repo_name=project_path)
            clone_token = github_client.get_clone_token()
            if clone_token and clone_token != "your_github_personal_access_token_here":
                return f"https://x-access-token:{clone_token}@github.com/{project_path}.git"
        except Exception as e:
            logger.warning(f"Failed to get GitHub client clone token: {e}")
        return f"https://github.com/{project_path}.git"


async def _set_rag_status(repo_id: int, status: str) -> None:
    """Updates the rag_status inside the repository settings JSON."""
    async with get_db_session_context() as session:
        repo = await RepositoryRepo.get_by_id(session, repo_id)
        if not repo:
            return
        
        current_settings = repo.settings or {}
        current_settings["rag_status"] = status
        
        stmt = update(Repository).where(Repository.id == repo_id).values(settings=current_settings)
        await session.execute(stmt)


@celery_app.task(
    name="workers.rag_worker.update_repo_rag_index",
    bind=True,
    time_limit=3600,
    soft_time_limit=3500,
    max_retries=1,
)
def update_repo_rag_index(self, repo_id: int) -> dict[str, Any]:
    """Celery task that fetches a repository, clones it, and builds a persistent RAG index."""
    # Reset SQLAlchemy engine for asyncio run context
    from models import database as _db
    _db._engine = None
    _db._session_factory = None

    return asyncio.run(_update_repo_rag_index_async(repo_id))


async def _update_repo_rag_index_async(repo_id: int) -> dict[str, Any]:
    logger.info(f"Starting RAG index update for repo_id={repo_id}")
    
    async with get_db_session_context() as session:
        repo = await RepositoryRepo.get_by_id(session, repo_id)
        if not repo:
            return {"success": False, "error": "Repo not found"}
        repo_url = _get_repo_clone_url(repo)

    await _set_rag_status(repo_id, "building")

    try:
        with RepoCloner(repo_url=repo_url) as cloner:
            repo_path = cloner.get_repo_path()
            rag_cfg = get_rag_settings()
            repo_files = []
            
            for root, dirs, files in os.walk(repo_path):
                dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__', '.venv', 'dist', 'build', '.next')]
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext in rag_cfg.code_extensions:
                        file_path = os.path.join(root, file)
                        if os.path.getsize(file_path) <= rag_cfg.RAG_MAX_FILE_BYTES:
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    repo_files.append({"file_path": file_path, "content": f.read()})
                            except Exception:
                                pass
                                
            if not repo_files:
                await _set_rag_status(repo_id, "ready")
                return {"success": True, "chunks": 0}

            chunker = ASTChunker()
            chunks = chunker.chunk_files(repo_files)
            
            retriever = HybridRetriever(get_embedding_model())
            retriever.build(chunks)
            
            index_dir = os.path.join("data", "rag_v2", f"repo_{repo_id}")
            os.makedirs(index_dir, exist_ok=True)
            retriever.save(index_dir)

        await _set_rag_status(repo_id, "ready")
        return {"success": True, "chunks": len(chunks)}
        
    except Exception as e:
        logger.error(f"Failed to build RAG index for repo_id={repo_id}: {e}")
        await _set_rag_status(repo_id, "failed")
        return {"success": False, "error": str(e)}
