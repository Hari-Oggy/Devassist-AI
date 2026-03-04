"""
Documentation worker — Celery task that runs the DocumentationAgent asynchronously.
"""

from taskqueue.celery_app import celery_app
from core.config import get_settings
from core.logger import get_logger

logger = get_logger("workers.doc")
settings = get_settings()


@celery_app.task(
    name="workers.doc_worker.run_documentation",
    bind=True,
    time_limit=settings.DOC_TIMEOUT + 30,
    soft_time_limit=settings.DOC_TIMEOUT,
    max_retries=1,
)
def run_documentation(self, file_path: str, save_updated: bool = False) -> dict:
    """
    Execute documentation generation as a background task.

    Args:
        file_path: Absolute path to the Python file.
        save_updated: Whether to write updated code back to file.

    Returns:
        Documentation result dict.
    """
    logger.info(f"Starting documentation task for {file_path}")

    try:
        from agents.doc_agent import DocumentationAgent
        agent = DocumentationAgent()
        result = agent.process_file(file_path, save_updated)
        logger.info(f"Documentation task completed for {file_path}")
        return result
    except Exception as e:
        logger.error(f"Documentation task failed for {file_path}: {e}")
        return {
            "file": file_path,
            "success": False,
            "error": str(e),
        }
