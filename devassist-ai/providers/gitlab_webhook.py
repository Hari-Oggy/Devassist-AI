"""
GitLab Webhook Handler — DevAssist-AI Phase 5.

Handles incoming GitLab webhook events for merge requests.
Maintained separately from api/webhook.py (GitHub handler) so both
integrations are independently testable and deployable.

Supported events (X-Gitlab-Event header):
    - Merge Request Hook → triggers review on opened/updated MRs
    - Note Hook           → responds to MR comments mentioning the bot

Verification:
    GitLab signs payloads with a secret token sent in the
    X-Gitlab-Token header. We compare it with GITLAB_WEBHOOK_SECRET
    from settings (constant-time comparison to prevent timing attacks).

Mount this router in api/main.py:
    app.include_router(gitlab_webhook_router, prefix="/webhooks/gitlab")
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

from core.logger import get_logger
from core.config import get_settings

logger = get_logger("providers.gitlab_webhook")
settings = get_settings()

router = APIRouter(tags=["gitlab-webhook"])

# GitLab MR actions that should trigger a review
_REVIEW_ACTIONS = {"open", "reopen", "update"}


# ── Main webhook endpoint ──────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_202_ACCEPTED)
async def handle_gitlab_webhook(
    request: Request,
    x_gitlab_event: str = Header(default=""),
    x_gitlab_token: str = Header(default=""),
) -> dict[str, str]:
    """Receive and dispatch GitLab webhook events.

    Verifies the webhook secret, then delegates to the appropriate
    event handler based on the ``X-Gitlab-Event`` header.

    Args:
        request: Raw FastAPI request (payload read from body).
        x_gitlab_event: GitLab event type header.
        x_gitlab_token: Secret token for verification.

    Returns:
        Dict with ``status`` and ``message`` keys.

    Raises:
        HTTPException 403: When webhook secret verification fails.
        HTTPException 400: When payload cannot be parsed.
    """
    # 1. Verify secret
    _verify_gitlab_secret(x_gitlab_token)

    # 2. Parse payload
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    event_type = x_gitlab_event.strip()
    logger.info("GitLab webhook received: %s", event_type)

    # 3. Dispatch
    if event_type == "Merge Request Hook":
        return await _handle_merge_request_event(payload)
    elif event_type == "Note Hook":
        return await _handle_note_event(payload)
    else:
        logger.debug("GitLab webhook: unhandled event type '%s'", event_type)
        return {"status": "ignored", "message": f"Event '{event_type}' not handled"}


# ── Event handlers ─────────────────────────────────────────────────────

async def _handle_merge_request_event(payload: dict[str, Any]) -> dict[str, str]:
    """Handle Merge Request Hook events.

    Triggers a review when an MR is opened, reopened, or updated with
    a new commit (push to source branch).
    """
    mr_attrs = payload.get("object_attributes", {})
    action = mr_attrs.get("action", "")
    mr_iid = mr_attrs.get("iid")
    project = payload.get("project", {})
    project_path = project.get("path_with_namespace", "")

    logger.info(
        "GitLab MR event: action=%s mr_iid=%s project=%s",
        action, mr_iid, project_path,
    )

    if action not in _REVIEW_ACTIONS:
        return {
            "status": "skipped",
            "message": f"MR action '{action}' does not trigger a review",
        }

    if mr_attrs.get("work_in_progress", False) or mr_attrs.get("draft", False):
        logger.info("GitLab MR #%s is a draft — skipping review", mr_iid)
        return {"status": "skipped", "message": "Draft MR — review skipped"}

    # Extract key fields for the review job
    review_context = _extract_mr_context(payload, mr_attrs, project)

    # Enqueue the review task (async — does not block the webhook response)
    await _enqueue_gitlab_review(review_context)

    return {
        "status": "accepted",
        "message": f"Review queued for MR !{mr_iid} in {project_path}",
    }


async def _handle_note_event(payload: dict[str, Any]) -> dict[str, str]:
    """Handle Note Hook events (MR comments).

    Responds when the bot is mentioned in an MR comment (e.g. '@devassist review').
    """
    note = payload.get("object_attributes", {})
    note_body: str = note.get("note", "")
    noteable_type = note.get("noteable_type", "")

    if noteable_type != "MergeRequest":
        return {"status": "ignored", "message": "Note not on a MergeRequest"}

    bot_name = getattr(settings, "BOT_NAME", "devassist-ai")
    if f"@{bot_name}" not in note_body and "devassist" not in note_body.lower():
        return {"status": "ignored", "message": "Bot not mentioned in comment"}

    mr_attrs = payload.get("merge_request", {})
    mr_iid = mr_attrs.get("iid")
    project = payload.get("project", {})
    project_path = project.get("path_with_namespace", "")

    logger.info(
        "GitLab mention detected in MR !%s (%s) — queueing review",
        mr_iid, project_path,
    )

    review_context = _extract_mr_context(payload, mr_attrs, project)
    await _enqueue_gitlab_review(review_context)

    return {
        "status": "accepted",
        "message": f"Re-review queued for MR !{mr_iid} (mention trigger)",
    }


# ── Context extraction ─────────────────────────────────────────────────

def _extract_mr_context(
    payload: dict,
    mr_attrs: dict,
    project: dict,
) -> dict[str, Any]:
    """Extract a structured context dict from a GitLab webhook payload.

    Args:
        payload: Full webhook payload.
        mr_attrs: ``object_attributes`` sub-dict from the payload.
        project: ``project`` sub-dict from the payload.

    Returns:
        Dict with all fields needed to run a review job.
    """
    return {
        "provider": "gitlab",
        "project_path": project.get("path_with_namespace", ""),
        "project_id": project.get("id"),
        "mr_iid": mr_attrs.get("iid"),
        "mr_title": mr_attrs.get("title", ""),
        "mr_author": payload.get("user", {}).get("username", ""),
        "source_branch": mr_attrs.get("source_branch", ""),
        "target_branch": mr_attrs.get("target_branch", ""),
        "last_commit_sha": mr_attrs.get("last_commit", {}).get("id", ""),
        "is_draft": mr_attrs.get("work_in_progress", False) or mr_attrs.get("draft", False),
        "mr_url": mr_attrs.get("url", ""),
        "action": mr_attrs.get("action", ""),
    }


# ── Task enqueueing ────────────────────────────────────────────────────

async def _enqueue_gitlab_review(context: dict[str, Any]) -> None:
    """Enqueue a GitLab MR review job.

    Currently logs the intent and delegates to the Celery task queue
    (when available). Falls back to a no-op with logging in dev mode.

    Args:
        context: MR context dict from :func:`_extract_mr_context`.
    """
    logger.info(
        "Enqueueing GitLab review: project=%s mr=!%s sha=%s",
        context.get("project_path"),
        context.get("mr_iid"),
        context.get("last_commit_sha", "")[:8],
    )
    from workers.review_worker import run_review
    run_review.delay(context)


# ── Secret verification ────────────────────────────────────────────────

def _verify_gitlab_secret(token_header: str) -> None:
    """Verify the GitLab webhook secret token.

    GitLab sends the secret as a plain token in X-Gitlab-Token (not HMAC).
    We use hmac.compare_digest to prevent timing attacks.

    Args:
        token_header: Value from X-Gitlab-Token request header.

    Raises:
        HTTPException 403: If the token does not match.
    """
    expected = getattr(settings, "GITLAB_WEBHOOK_SECRET", "") or ""
    if not expected:
        # Secret not configured — skip verification (dev mode)
        logger.warning(
            "GITLAB_WEBHOOK_SECRET not set — webhook verification disabled!"
        )
        return

    if not hmac.compare_digest(
        token_header.encode("utf-8"),
        expected.encode("utf-8"),
    ):
        logger.warning("GitLab webhook secret mismatch")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook token",
        )
