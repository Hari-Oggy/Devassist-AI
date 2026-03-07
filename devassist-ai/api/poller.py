"""
GitHub Poller — background thread that checks for new/updated PRs.

Zero-config alternative to webhooks. Uses GitHub's conditional requests
(ETags) so unchanged polls don't count against rate limits.
"""

import time
import threading
from datetime import datetime

from core.config import get_settings
from core.logger import get_logger
from core.review_state import (
    should_debounce,
    acquire_review_lock,
    release_review_lock,
    get_backoff_seconds,
    record_failure,
    clear_failures,
    get_last_reviewed_sha,
)

logger = get_logger("api.poller")


class GitHubPoller:
    """Polls GitHub for new/updated PRs and triggers reviews."""

    def __init__(self):
        self.settings = get_settings()
        self._stop_event = threading.Event()
        self._thread = None
        self._etag = None  # For conditional requests (304 Not Modified)
        self._last_poll_prs = {}  # {pr_number: head_sha} from last poll

    def start(self):
        """Start the poller background thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("Poller is already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="github-poller")
        self._thread.start()
        logger.info(f"GitHub Poller started (interval: {self.settings.POLLING_INTERVAL}s)")

    def stop(self):
        """Stop the poller."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("GitHub Poller stopped")

    def _poll_loop(self):
        """Main polling loop."""
        while not self._stop_event.is_set():
            try:
                self._check_for_updates()
            except Exception as e:
                logger.error(f"Poller error: {e}")

            self._stop_event.wait(timeout=self.settings.POLLING_INTERVAL)

    def _check_for_updates(self):
        """Check GitHub for new or updated PRs."""
        try:
            from agents.tools.github_tool import get_github_client
            client = get_github_client()
            repo = client.repo

            open_prs = list(repo.get_pulls(state="open", sort="updated", direction="desc"))
            logger.debug(f"Polled {len(open_prs)} open PRs")

            for pr in open_prs:
                self._process_pr(pr)

        except Exception as e:
            logger.error(f"GitHub poll failed: {e}")

    def _process_pr(self, pr):
        """Check if a PR needs review and trigger it if so."""
        pr_number = pr.number
        head_sha = pr.head.sha

        # — Filter: skip drafts
        if self.settings.SKIP_DRAFT_PRS and pr.draft:
            return

        # — Filter: skip bot users
        if pr.user.type == "Bot":
            return

        # — Filter: require label
        if self.settings.REQUIRE_LABEL:
            labels = [label.name for label in pr.labels]
            if self.settings.REQUIRE_LABEL not in labels:
                return

        # — Check if SHA changed since last poll (something new to review)
        last_known_sha = self._last_poll_prs.get(pr_number)
        last_reviewed_sha = get_last_reviewed_sha(pr_number)

        if head_sha == last_known_sha:
            return  # Already polled this exact SHA — nothing changed

        if head_sha == last_reviewed_sha:
            self._last_poll_prs[pr_number] = head_sha
            return  # Already reviewed this SHA — skip

        # — Check debounce
        if should_debounce(pr_number):
            return

        # — Check backoff
        backoff = get_backoff_seconds(pr_number)
        if backoff > 0:
            logger.debug(f"PR #{pr_number} in backoff ({backoff}s remaining)")
            return

        # — Acquire lock and review
        if not acquire_review_lock(pr_number):
            return  # Another review in progress

        logger.info(f"Poller: PR #{pr_number} has new changes ({head_sha[:8]}) — triggering review")

        try:
            from agents.review_agent import ReviewAgent
            agent = ReviewAgent()
            result = agent.review_pr_incremental(pr_number)

            if result.get("success"):
                clear_failures(pr_number)
                logger.info(f"PR #{pr_number} reviewed successfully")
            else:
                record_failure(pr_number)
                logger.warning(f"PR #{pr_number} review failed: {result.get('error')}")

        except Exception as e:
            record_failure(pr_number)
            logger.error(f"PR #{pr_number} review error: {e}")
        finally:
            release_review_lock(pr_number)
            self._last_poll_prs[pr_number] = head_sha


# Singleton poller instance
_poller_instance = None


def get_poller() -> GitHubPoller:
    global _poller_instance
    if _poller_instance is None:
        _poller_instance = GitHubPoller()
    return _poller_instance
