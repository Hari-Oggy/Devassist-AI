"""
Conversation worker — Celery task that runs the ConversationAgent asynchronously.
"""

from taskqueue.celery_app import celery_app
from core.config import get_settings
from core.logger import get_logger

logger = get_logger("workers.conversation")
settings = get_settings()


@celery_app.task(
    name="workers.conversation_worker.run_conversation",
    bind=True,
    time_limit=settings.REVIEW_TIMEOUT + 30,
    soft_time_limit=settings.REVIEW_TIMEOUT,
    max_retries=1,
)
def run_conversation(self, pr_number: int, comment_id: int, user_comment: str) -> dict:
    """
    Execute a conversation response as a background task.

    Args:
        pr_number: GitHub PR number.
        comment_id: The comment ID to respond to.
        user_comment: The user's comment text.

    Returns:
        Conversation result dict.
    """
    logger.info(f"Starting conversation task for PR #{pr_number}, comment #{comment_id}")

    try:
        from agents.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        result = agent.respond(
            pr_number=pr_number,
            comment_id=comment_id,
            user_comment=user_comment,
        )
        logger.info(f"Conversation task completed for PR #{pr_number}")
        return result
    except Exception as e:
        logger.error(f"Conversation task failed for PR #{pr_number}: {e}")
        return {
            "pr_number": pr_number,
            "success": False,
            "error": str(e),
        }
