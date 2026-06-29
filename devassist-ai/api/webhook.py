"""
GitHub Webhook Handler — auto-triggers reviews on PR events.

Handles:
  - pull_request.opened / synchronize / reopened → triggers review
  - pull_request.closed (merged) → triggers documentation generation
  - issue_comment.created → triggers conversation response
"""

import asyncio
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


async def _trigger_review(pr_number: int, action: str, context: dict):
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
        task = run_review.delay(context)
        logger.info(f"PR #{pr_number} review queued as task {task.id}")
        return {"status": "queued", "pr_number": pr_number, "task_id": task.id}
    except Exception as celery_err:
        logger.warning(f"Celery unavailable ({celery_err}), falling back to local async review")
        
        # Local fallback using the exact same modern pipeline logic
        try:
            from workers.review_worker import _run_review_async
            # Run in the background of the FastAPI event loop to not block the webhook response
            asyncio.create_task(_run_review_async(context))
            return {"status": "fallback_queued", "pr_number": pr_number}
        except Exception as fallback_err:
            logger.error(f"Fallback review error: {fallback_err}")
            return {"status": "error", "error": str(fallback_err)}


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


def _trigger_documentation(pr_data: dict, repo_data: dict):
    """Dispatch documentation generation to Celery worker when a PR is merged."""
    pr_number = pr_data.get("number")
    repo_full_name = repo_data.get("full_name", "")

    # Collect merged file paths from PR (best-effort via context)
    # We pass the repo name so the doc agent can clone if needed
    payload = {
        "repo": repo_full_name,
        "pr_number": pr_number,
        "merge_commit_sha": pr_data.get("merge_commit_sha", ""),
        "base_branch": pr_data.get("base", {}).get("ref", ""),
    }

    try:
        from workers.doc_worker import run_documentation
        task = run_documentation.delay(
            file_path=repo_full_name,  # doc_agent interprets this as a repo identifier
            save_updated=False,
        )
        logger.info(f"Documentation task queued for merged PR #{pr_number} as {task.id}")
        return {"status": "queued", "pr_number": pr_number, "task_id": task.id}
    except Exception as e:
        logger.warning(f"Failed to queue documentation task for PR #{pr_number}: {e}")
        return {"status": "skipped", "reason": str(e)}


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
        repo_data = data.get("repository", {})
        context = {
            "provider": "github",
            "project_path": repo_data.get("full_name", ""),
            "project_id": repo_data.get("id"),
            "pr_number": pr_number,
            "mr_title": pr_data.get("title", ""),
            "mr_author": pr_data.get("user", {}).get("login", ""),
            "source_branch": pr_data.get("head", {}).get("ref", ""),
            "target_branch": pr_data.get("base", {}).get("ref", ""),
            "is_draft": pr_data.get("draft", False),
            "mr_url": pr_data.get("html_url", ""),
            "last_commit_sha": pr_data.get("head", {}).get("sha", ""),
            "installation_id": data.get("installation", {}).get("id"),
        }
        result = await _trigger_review(pr_number, action, context)
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

    # ─── Pull Request Merged — Documentation Generation ───────────────────
    if event == "pull_request" and action == "closed":
        pr_data = data.get("pull_request", {})
        if pr_data.get("merged", False):
            pr_number = pr_data.get("number")
            repo_data = data.get("repository", {})
            logger.info(f"Webhook: PR #{pr_number} merged — triggering documentation")
            result = _trigger_documentation(pr_data, repo_data)
            
            # --- Added for RAG ---
            # Trigger RAG index refresh
            try:
                from models.database import get_db_session_context
                from models.repositories import RepositoryRepo
                from workers.rag_worker import update_repo_rag_index
                
                async def dispatch_rag_update():
                    async with get_db_session_context() as session:
                        repo = await RepositoryRepo.get_by_full_name(session, "github", repo_data.get("full_name", ""))
                        if repo:
                            update_repo_rag_index.delay(repo.id)
                            logger.info(f"Triggered RAG update for repo_id={repo.id} (PR Merged)")
                
                asyncio.create_task(dispatch_rag_update())
            except Exception as e:
                logger.warning(f"Failed to queue RAG update on merge: {e}")
            # ---------------------
            
            return {"status": "documentation_triggered", "pr_number": pr_number, "result": result}
        return {"status": "ignored", "reason": "PR closed but not merged"}

    # ─── Push Events (Default Branch) ──────────────────────────────────────────
    if event == "push":
        ref = data.get("ref", "")
        repo_data = data.get("repository", {})
        default_branch = repo_data.get("default_branch", "main")
        
        if ref == f"refs/heads/{default_branch}":
            try:
                from models.database import get_db_session_context
                from models.repositories import RepositoryRepo
                from workers.rag_worker import update_repo_rag_index
                
                async def dispatch_rag_update_on_push():
                    async with get_db_session_context() as session:
                        repo = await RepositoryRepo.get_by_full_name(session, "github", repo_data.get("full_name", ""))
                        if repo:
                            update_repo_rag_index.delay(repo.id)
                            logger.info(f"Triggered RAG update for repo_id={repo.id} (Push to default branch)")
                
                asyncio.create_task(dispatch_rag_update_on_push())
                return {"status": "rag_update_triggered", "branch": default_branch}
            except Exception as e:
                logger.warning(f"Failed to queue RAG update on push: {e}")
                return {"status": "error", "error": str(e)}

    return {"status": "ignored", "event": event, "action": action}
