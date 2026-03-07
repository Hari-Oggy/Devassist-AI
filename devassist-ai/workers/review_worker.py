"""
Review worker — Celery task that runs the ReviewAgent asynchronously.
"""

from taskqueue.celery_app import celery_app
from core.config import get_settings
from core.logger import get_logger

logger = get_logger("workers.review")
settings = get_settings()


@celery_app.task(
    name="workers.review_worker.run_review",
    bind=True,
    time_limit=settings.REVIEW_TIMEOUT + 30,
    soft_time_limit=settings.REVIEW_TIMEOUT,
    max_retries=1,
)
def run_review(self, pr_number: int) -> dict:
    """
    Execute a full PR review as a background task.

    Args:
        pr_number: GitHub PR number to review.

    Returns:
        Review result dict with comments, audit log, etc.
    """
    logger.info(f"Starting review task for PR #{pr_number}")

    try:
        from agents.review_agent import ReviewAgent
        agent = ReviewAgent()
        result = agent.review_pr(pr_number)
        logger.info(f"Review task completed for PR #{pr_number}")
        return result
    except Exception as e:
        logger.error(f"Review task failed for PR #{pr_number}: {e}")
        return {
            "pr_number": pr_number,
            "success": False,
            "error": str(e),
            "comments": [],
            "audit_log": [],
        }
