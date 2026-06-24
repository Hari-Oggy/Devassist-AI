"""
GitLab Polling Mode — DevAssist-AI Phase 5.

Alternative to webhooks for GitLab instances where outbound webhooks
are not available (e.g., self-hosted GitLab behind a firewall).

Polls configured projects for new or updated MRs at a configurable interval.
Maintains a state file to track which MRs have already been reviewed,
preventing duplicate review submissions.

Maintained separately from api/poller.py (GitHub polling) so both
providers are independently configurable and maintainable.

Environment variables:
    GITLAB_TOKEN              — Personal/Project Access Token
    GITLAB_PROJECTS           — Comma-separated list of project paths to poll
    GITLAB_POLL_INTERVAL      — Seconds between polls (default: 60)
    GITLAB_POLLER_STATE_PATH  — Path to JSON state file (default: ./data/gitlab_poller_state.json)
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from core.logger import get_logger
from core.config import get_settings
from providers.gitlab_client import GitLabClient

logger = get_logger("providers.gitlab_poller")


class GitLabPollerState:
    """Persistent state tracking for the GitLab poller.

    Stores the last-seen updated_at timestamp and seen MR IIDs per project
    to avoid re-reviewing MRs that have already been processed.
    """

    def __init__(self, state_path: str) -> None:
        self._path = state_path
        self._state: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._state = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, default=str)

    def get_seen_shas(self, project_path: str) -> dict[int, str]:
        """Return {mr_iid: last_commit_sha} for seen MRs in a project."""
        return self._state.get(project_path, {})

    def mark_reviewed(
        self, project_path: str, mr_iid: int, commit_sha: str
    ) -> None:
        """Record that an MR has been reviewed at a given commit SHA."""
        if project_path not in self._state:
            self._state[project_path] = {}
        self._state[project_path][str(mr_iid)] = commit_sha
        self._save()

    def needs_review(
        self, project_path: str, mr_iid: int, current_sha: str
    ) -> bool:
        """Return True if this MR has not been reviewed at this SHA."""
        seen = self.get_seen_shas(project_path)
        return seen.get(str(mr_iid)) != current_sha


class GitLabPoller:
    """Async GitLab poller that checks for new/updated MRs periodically.

    Example::

        poller = GitLabPoller()
        await poller.start()   # runs until cancelled

    Each poll cycle:
        1. For each configured project, fetch open MRs
        2. For each MR, check if the latest commit SHA is new
        3. If new, enqueue a review and mark the SHA as seen
    """

    DEFAULT_INTERVAL = 60  # seconds
    DEFAULT_STATE_PATH = "./data/gitlab_poller_state.json"

    def __init__(
        self,
        projects: Optional[list[str]] = None,
        interval: Optional[int] = None,
        state_path: Optional[str] = None,
    ) -> None:
        settings = get_settings()

        # Parse comma-separated project list from env if not provided
        raw_projects = getattr(settings, "GITLAB_PROJECTS", "") or ""
        self._projects: list[str] = projects or [
            p.strip() for p in raw_projects.split(",") if p.strip()
        ]

        self._interval: int = interval or int(
            getattr(settings, "GITLAB_POLL_INTERVAL", self.DEFAULT_INTERVAL)
        )
        self._state_path: str = state_path or getattr(
            settings, "GITLAB_POLLER_STATE_PATH", self.DEFAULT_STATE_PATH
        )
        self._state = GitLabPollerState(self._state_path)
        self._running = False

    # ── Public API ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the polling loop (runs until :meth:`stop` is called).

        Runs one immediate poll cycle on start, then waits for the
        configured interval before each subsequent cycle.
        """
        if not self._projects:
            logger.warning(
                "GitLabPoller: no projects configured (set GITLAB_PROJECTS). "
                "Poller will not run."
            )
            return

        logger.info(
            "GitLabPoller starting: projects=%s interval=%ds",
            self._projects, self._interval,
        )
        self._running = True

        while self._running:
            try:
                await self._poll_cycle()
            except Exception as exc:
                logger.error("GitLabPoller poll cycle error: %s", exc)

            if not self._running:
                break
            await asyncio.sleep(self._interval)

    def stop(self) -> None:
        """Signal the polling loop to stop after the current cycle."""
        logger.info("GitLabPoller stopping...")
        self._running = False

    # ── Poll cycle ─────────────────────────────────────────────────────

    async def _poll_cycle(self) -> None:
        """Run one full poll across all configured projects."""
        logger.debug("GitLabPoller: starting poll cycle for %d projects", len(self._projects))

        async with GitLabClient() as client:
            for project_path in self._projects:
                try:
                    await self._poll_project(client, project_path)
                except Exception as exc:
                    logger.error(
                        "GitLabPoller: error polling %s: %s", project_path, exc
                    )

    async def _poll_project(self, client: GitLabClient, project_path: str) -> None:
        """Poll a single project for reviewable MRs.

        Args:
            client: Authenticated GitLabClient.
            project_path: GitLab project path (e.g. 'group/repo').
        """
        open_mrs = await client.list_open_mrs(project_path)
        logger.debug(
            "GitLabPoller: %s — %d open MRs", project_path, len(open_mrs)
        )

        for mr in open_mrs:
            mr_iid: int = mr.get("iid", 0)
            is_draft: bool = mr.get("work_in_progress", False) or mr.get("draft", False)

            if is_draft:
                continue

            # Get last commit SHA
            last_commit = mr.get("sha") or mr.get("diff_refs", {}).get("head_sha", "")

            if not last_commit:
                continue

            if not self._state.needs_review(project_path, mr_iid, last_commit):
                logger.debug(
                    "GitLabPoller: MR !%d already reviewed at sha=%s",
                    mr_iid, last_commit[:8],
                )
                continue

            # New commit — enqueue review
            context = {
                "provider": "gitlab",
                "project_path": project_path,
                "mr_iid": mr_iid,
                "mr_title": mr.get("title", ""),
                "mr_author": mr.get("author", {}).get("username", ""),
                "source_branch": mr.get("source_branch", ""),
                "target_branch": mr.get("target_branch", ""),
                "last_commit_sha": last_commit,
                "mr_url": mr.get("web_url", ""),
                "action": "poll",
            }

            logger.info(
                "GitLabPoller: queuing review for %s MR !%d (sha=%s)",
                project_path, mr_iid, last_commit[:8],
            )

            await self._enqueue_review(context)
            self._state.mark_reviewed(project_path, mr_iid, last_commit)

    async def _enqueue_review(self, context: dict[str, Any]) -> None:
        """Submit a review job to the task queue.

        Args:
            context: MR context dict for the review worker.
        """
        # TODO (Phase 5 integration): submit to Celery task queue
        # from workers.review_worker import run_gitlab_review
        # run_gitlab_review.delay(context)
        logger.info(
            "GitLabPoller: [stub] review enqueued for %s MR !%s",
            context.get("project_path"), context.get("mr_iid"),
        )

    @property
    def is_running(self) -> bool:
        """Return True if the polling loop is active."""
        return self._running

    @property
    def configured_projects(self) -> list[str]:
        """Return the list of projects being polled."""
        return list(self._projects)
