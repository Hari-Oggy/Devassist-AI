"""
GitHub Webhook Handler — auto-triggers reviews on PR events.

Handles:
  - pull_request.opened / synchronize / reopened → triggers review
  - issue_comment.created → triggers conversation response
"""

import hashlib
import hmac
import json
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException
from core.config import get_settings
from core.logger import get_logger
from core.review_state import (
    should_debounce,
    acquire_review_lock,
    release_review_lock,
    get_backoff_seconds,
    record_failure,
    clear_failures,
    BOT_MARKER,
)

logger = get_logger("api.webhook")
settings = get_settings()

router = APIRouter()


def _verify_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not settings.WEBHOOK_SECRET:
        return True  # No secret configured — skip verification (dev mode)

    expected = "sha256=" + hmac.HMAC(
        settings.WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _should_skip_pr(pr_data: dict) -> tuple[bool, str]:
    """Check if a PR should be skipped based on filters."""
    # Skip drafts
    if settings.SKIP_DRAFT_PRS and pr_data.get("draft", False):
        return True, "draft PR"

    # Skip bot users
    user = pr_data.get("user", {})
    user_type = user.get("type", "")
    user_login = user.get("login", "")
    if user_type == "Bot" or user_login in ("dependabot[bot]", "renovate[bot]"):
        return True, f"bot user ({user_login})"

    # Require label
    if settings.REQUIRE_LABEL:
        labels = [l.get("name", "") for l in pr_data.get("labels", [])]
        if settings.REQUIRE_LABEL not in labels:
            return True, f"missing required label '{settings.REQUIRE_LABEL}'"

    return False, ""


def _trigger_review(pr_number: int, action: str):
    """Dispatch review to Celery worker (non-blocking). Falls back to sync if unavailable."""
    # Check debounce
    if should_debounce(pr_number):
        logger.info(f"PR #{pr_number} debounced — skipping review")
        return {"status": "debounced", "pr_number": pr_number}

    # Check backoff
    backoff = get_backoff_seconds(pr_number)
    if backoff > 0:
        logger.info(f"PR #{pr_number} in backoff — {backoff}s remaining")
        return {"status": "backoff", "pr_number": pr_number, "retry_in": backoff}

    # Try async dispatch via Celery
    try:
        from workers.review_worker import run_review
        task = run_review.delay(pr_number)
        logger.info(f"PR #{pr_number} review queued as task {task.id}")
        return {"status": "queued", "pr_number": pr_number, "task_id": task.id}
    except Exception as celery_err:
        logger.warning(f"Celery unavailable ({celery_err}), falling back to sync review")

    # Sync fallback — acquire lock to prevent concurrent reviews
    if not acquire_review_lock(pr_number):
        logger.info(f"PR #{pr_number} already locked — review in progress")
        return {"status": "locked", "pr_number": pr_number}

    try:
        from agents.review_agent import ReviewAgent
        agent = ReviewAgent()
        result = agent.review_pr_incremental(pr_number)

        if result.get("success"):
            clear_failures(pr_number)
            logger.info(f"PR #{pr_number} review complete: {len(result.get('comments', []))} comments posted")
        else:
            record_failure(pr_number)
            logger.warning(f"PR #{pr_number} review failed: {result.get('error')}")

        return result
    except Exception as e:
        record_failure(pr_number)
        logger.error(f"PR #{pr_number} review error: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        release_review_lock(pr_number)


def _trigger_conversation(pr_number: int, comment_data: dict):
    """Dispatch conversation response to Celery worker (non-blocking). Falls back to sync."""
    comment_id = comment_data.get("id")
    user_comment = comment_data.get("body", "")

    # Try async dispatch via Celery
    try:
        from workers.conversation_worker import run_conversation
        task = run_conversation.delay(pr_number, comment_id, user_comment)
        logger.info(f"Conversation for PR #{pr_number} queued as task {task.id}")
        return {"status": "queued", "pr_number": pr_number, "task_id": task.id}
    except Exception as celery_err:
        logger.warning(f"Celery unavailable ({celery_err}), falling back to sync conversation")

    # Sync fallback
    try:
        from agents.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        return agent.respond(
            pr_number=pr_number,
            comment_id=comment_id,
            user_comment=user_comment,
        )
    except Exception as e:
        logger.error(f"Conversation response failed: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/webhook")
async def github_webhook(request: Request):
    """Receive and process GitHub webhook events."""
    event = request.headers.get("X-GitHub-Event", "")
    signature = request.headers.get("X-Hub-Signature-256", "")
    payload = await request.body()

    # Verify signature
    if not _verify_signature(payload, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Handle ping (GitHub sends this when you first set up the webhook)
    if event == "ping":
        logger.info("Webhook ping received — connection verified!")
        return {"status": "pong", "timestamp": datetime.now().isoformat()}

    data = json.loads(payload)
    action = data.get("action", "")

    # ─── Pull Request Events ──────────────────────────────────────────────
    if event == "pull_request" and action in ("opened", "synchronize", "reopened"):
        pr_data = data.get("pull_request", {})
        pr_number = pr_data.get("number")

        skip, reason = _should_skip_pr(pr_data)
        if skip:
            logger.info(f"Skipping PR #{pr_number}: {reason}")
            return {"status": "skipped", "reason": reason}

        logger.info(f"Webhook: PR #{pr_number} {action} — triggering review")
        result = _trigger_review(pr_number, action)
        return {"status": "review_triggered", "pr_number": pr_number, "result": result}

    # ─── Issue Comment Events (Conversation Threading) ────────────────────
    if event == "issue_comment" and action == "created":
        comment = data.get("comment", {})
        issue = data.get("issue", {})

        # Only respond if it's a PR comment (issues have no pull_request key)
        if "pull_request" not in issue:
            return {"status": "ignored", "reason": "not a PR comment"}

        # Don't respond to our own comments
        if BOT_MARKER in comment.get("body", ""):
            return {"status": "ignored", "reason": "own comment"}

        # Check if this is a reply to one of our bot comments
        # (GitHub doesn't directly tell us, so we check if the comment
        # quotes or mentions the bot)
        pr_number = issue.get("number")
        logger.info(f"Webhook: Comment on PR #{pr_number} — triggering conversation")
        result = _trigger_conversation(pr_number, comment)
        return {"status": "conversation_triggered", "pr_number": pr_number, "result": result}

    return {"status": "ignored", "event": event, "action": action}
