"""
Tests for Phase 5: GitLab client, webhook handler, and poller.
No live GitLab API calls — all HTTP interactions are mocked.
"""

from __future__ import annotations

import json
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── GitLabClient ───────────────────────────────────────────────────────

class TestGitLabClientPathEncoding:
    def test_encode_simple_path(self):
        from providers.gitlab_client import _encode_path
        assert _encode_path("group/repo") == "group%2Frepo"

    def test_encode_nested_path(self):
        from providers.gitlab_client import _encode_path
        assert _encode_path("top/sub/repo") == "top%2Fsub%2Frepo"

    def test_encode_numeric_id(self):
        from providers.gitlab_client import _encode_path
        assert _encode_path("12345") == "12345"


class TestGitLabClientInit:
    def test_init_defaults(self):
        from providers.gitlab_client import GitLabClient
        client = GitLabClient(token="test-token")
        assert client._token == "test-token"
        assert "gitlab.com" in client._base_url

    def test_custom_base_url(self):
        from providers.gitlab_client import GitLabClient
        client = GitLabClient(
            token="tok",
            base_url="https://git.mycompany.com/api/v4",
        )
        assert "mycompany" in client._base_url

    def test_trailing_slash_stripped(self):
        from providers.gitlab_client import GitLabClient
        client = GitLabClient(token="t", base_url="https://gitlab.com/api/v4/")
        assert not client._base_url.endswith("/")


class TestGitLabClientMrDiffAsText:
    @pytest.mark.asyncio
    async def test_diff_as_text_from_diffs(self):
        """get_mr_diff_as_text should concatenate diff hunks with headers."""
        from providers.gitlab_client import GitLabClient

        client = GitLabClient(token="tok")
        client._client = MagicMock()  # prevent "not in context manager" error

        diffs = [
            {"old_path": "a.py", "new_path": "a.py", "diff": "@@ -1 +1 @@\n-old\n+new\n"},
            {"old_path": "b.py", "new_path": "b.py", "diff": "@@ -5 +5 @@\n-x\n+y\n"},
        ]

        with patch.object(client, "get_mr_diff", new=AsyncMock(return_value=diffs)):
            text = await client.get_mr_diff_as_text("group/repo", 42)

        assert "--- a/a.py" in text
        assert "+++ b/a.py" in text
        assert "-old" in text
        assert "+new" in text


# ── GitLab Webhook ─────────────────────────────────────────────────────

class TestGitLabWebhookSecretVerification:
    def test_missing_secret_passes_with_warning(self):
        """When no secret is configured, verification should not raise."""
        from providers.gitlab_webhook import _verify_gitlab_secret
        with patch("providers.gitlab_webhook.settings") as mock_settings:
            mock_settings.GITLAB_WEBHOOK_SECRET = ""
            # Should not raise
            _verify_gitlab_secret("anything")

    def test_correct_secret_passes(self):
        from providers.gitlab_webhook import _verify_gitlab_secret
        with patch("providers.gitlab_webhook.settings") as mock_settings:
            mock_settings.GITLAB_WEBHOOK_SECRET = "my-secret-token"
            _verify_gitlab_secret("my-secret-token")  # should not raise

    def test_wrong_secret_raises_403(self):
        from providers.gitlab_webhook import _verify_gitlab_secret
        from fastapi import HTTPException
        with patch("providers.gitlab_webhook.settings") as mock_settings:
            mock_settings.GITLAB_WEBHOOK_SECRET = "correct-secret"
            with pytest.raises(HTTPException) as exc_info:
                _verify_gitlab_secret("wrong-secret")
            assert exc_info.value.status_code == 403


class TestExtractMrContext:
    def test_extracts_all_fields(self):
        from providers.gitlab_webhook import _extract_mr_context
        payload = {
            "user": {"username": "alice"},
            "project": {
                "path_with_namespace": "group/repo",
                "id": 123,
            },
        }
        mr_attrs = {
            "iid": 42,
            "title": "Fix bug",
            "source_branch": "fix/bug",
            "target_branch": "main",
            "last_commit": {"id": "deadbeef"},
            "work_in_progress": False,
            "url": "https://gitlab.com/group/repo/-/merge_requests/42",
            "action": "open",
        }
        ctx = _extract_mr_context(payload, mr_attrs, payload["project"])
        assert ctx["provider"] == "gitlab"
        assert ctx["project_path"] == "group/repo"
        assert ctx["mr_iid"] == 42
        assert ctx["mr_title"] == "Fix bug"
        assert ctx["source_branch"] == "fix/bug"
        assert ctx["last_commit_sha"] == "deadbeef"
        assert ctx["is_draft"] is False
        assert ctx["mr_author"] == "alice"


class TestHandleMergeRequestEvent:
    @pytest.mark.asyncio
    async def test_skips_closed_action(self):
        from providers.gitlab_webhook import _handle_merge_request_event
        payload = {
            "user": {},
            "project": {"path_with_namespace": "g/r", "id": 1},
            "object_attributes": {
                "iid": 1, "title": "PR", "action": "close",
                "source_branch": "feat", "target_branch": "main",
                "last_commit": {"id": "abc"},
                "work_in_progress": False,
                "url": "",
            },
        }
        result = await _handle_merge_request_event(payload)
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_skips_draft_mr(self):
        from providers.gitlab_webhook import _handle_merge_request_event
        payload = {
            "user": {},
            "project": {"path_with_namespace": "g/r", "id": 1},
            "object_attributes": {
                "iid": 2, "title": "[WIP] PR", "action": "open",
                "source_branch": "feat", "target_branch": "main",
                "last_commit": {"id": "abc"},
                "work_in_progress": True,
                "url": "",
            },
        }
        result = await _handle_merge_request_event(payload)
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_accepts_open_action(self):
        from providers.gitlab_webhook import _handle_merge_request_event
        payload = {
            "user": {},
            "project": {"path_with_namespace": "g/r", "id": 1},
            "object_attributes": {
                "iid": 3, "title": "New Feature", "action": "open",
                "source_branch": "feat", "target_branch": "main",
                "last_commit": {"id": "abc123"},
                "work_in_progress": False, "draft": False,
                "url": "https://gitlab.com/g/r/-/merge_requests/3",
            },
        }
        result = await _handle_merge_request_event(payload)
        assert result["status"] == "accepted"


class TestHandleNoteEvent:
    @pytest.mark.asyncio
    async def test_ignores_non_mr_note(self):
        from providers.gitlab_webhook import _handle_note_event
        payload = {
            "object_attributes": {
                "note": "@devassist-ai review",
                "noteable_type": "Issue",
            },
        }
        result = await _handle_note_event(payload)
        assert result["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_ignores_note_without_mention(self):
        from providers.gitlab_webhook import _handle_note_event
        with patch("providers.gitlab_webhook.settings") as ms:
            ms.BOT_NAME = "devassist-ai"
            payload = {
                "object_attributes": {
                    "note": "Looks good to me!",
                    "noteable_type": "MergeRequest",
                },
                "merge_request": {"iid": 1},
                "project": {"path_with_namespace": "g/r", "id": 1},
                "user": {"username": "bob"},
            }
            result = await _handle_note_event(payload)
        assert result["status"] == "ignored"


# ── SSE Manager ────────────────────────────────────────────────────────

class TestSSEFormatEvent:
    def test_basic_event(self):
        from api.sse import format_sse_event
        output = format_sse_event({"review_id": 42, "type": "started"})
        assert "data:" in output
        assert "review_id" in output
        assert output.endswith("\n\n")

    def test_named_event(self):
        from api.sse import format_sse_event
        output = format_sse_event({"x": 1}, event="review_started")
        assert "event: review_started" in output

    def test_retry_included(self):
        from api.sse import format_sse_event
        output = format_sse_event({"x": 1}, retry_ms=3000)
        assert "retry: 3000" in output


class TestSSEManager:
    def test_init_empty(self):
        from api.sse import SSEManager
        m = SSEManager()
        assert m.total_clients == 0
        assert m.active_subscriptions == {}

    @pytest.mark.asyncio
    @patch('api.sse._get_redis', return_value=None)
    async def test_publish_no_subscribers(self, mock_get_redis):
        from api.sse import SSEManager
        m = SSEManager()
        sent = await m.publish(1, "review_started", "hello")
        assert sent == 0

    @pytest.mark.asyncio
    async def test_publish_reaches_subscriber(self):
        from api.sse import SSEManager
        import asyncio
        m = SSEManager()

        received = []

        async def consume():
            async for chunk in m.subscribe(review_id=5, timeout_seconds=2.0):
                received.append(chunk)
                if "review_completed" in chunk:
                    break

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)  # let the subscriber register

        await m.publish(5, "review_completed", "done", {"findings_count": 3})
        await asyncio.wait_for(task, timeout=3.0)

        assert any("review_completed" in r for r in received)

    @pytest.mark.asyncio
    @patch('api.sse._get_redis', return_value=None)
    async def test_total_clients_tracked(self, mock_get_redis):
        from api.sse import SSEManager
        import asyncio
        m = SSEManager()

        async def consume():
            gen = m.subscribe(review_id=10, timeout_seconds=0.5)
            await gen.__anext__() # get the connected event
            try:
                await gen.__anext__() # blocks on _subscribe_inprocess
            except StopAsyncIteration:
                pass

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)
        assert m.total_clients >= 1
        await asyncio.wait_for(task, timeout=2.0)


# ── GitLab Poller State ────────────────────────────────────────────────

class TestGitLabPollerState:
    def test_new_mr_needs_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            from providers.gitlab_poller import GitLabPollerState
            state = GitLabPollerState(os.path.join(tmp, "state.json"))
            assert state.needs_review("g/r", 1, "abc123") is True

    def test_mark_reviewed_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            from providers.gitlab_poller import GitLabPollerState
            path = os.path.join(tmp, "state.json")
            state = GitLabPollerState(path)
            state.mark_reviewed("g/r", 1, "abc123")
            # Reload
            state2 = GitLabPollerState(path)
            assert state2.needs_review("g/r", 1, "abc123") is False

    def test_new_sha_needs_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            from providers.gitlab_poller import GitLabPollerState
            state = GitLabPollerState(os.path.join(tmp, "state.json"))
            state.mark_reviewed("g/r", 1, "old_sha")
            # New commit SHA → needs review
            assert state.needs_review("g/r", 1, "new_sha") is True

    def test_same_sha_no_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            from providers.gitlab_poller import GitLabPollerState
            state = GitLabPollerState(os.path.join(tmp, "state.json"))
            state.mark_reviewed("g/r", 5, "fixed_sha")
            assert state.needs_review("g/r", 5, "fixed_sha") is False


class TestGitLabPollerInit:
    def test_no_projects_configured(self):
        from providers.gitlab_poller import GitLabPoller
        with patch("providers.gitlab_poller.get_settings") as ms:
            ms.return_value.GITLAB_PROJECTS = ""
            ms.return_value.GITLAB_POLL_INTERVAL = 60
            ms.return_value.GITLAB_POLLER_STATE_PATH = "./data/state.json"
            poller = GitLabPoller(projects=[])
        assert poller.configured_projects == []
        assert poller.is_running is False

    def test_projects_parsed_from_env(self):
        from providers.gitlab_poller import GitLabPoller
        with patch("providers.gitlab_poller.get_settings") as ms:
            ms.return_value.GITLAB_PROJECTS = "a/b,c/d, e/f "
            ms.return_value.GITLAB_POLL_INTERVAL = 30
            ms.return_value.GITLAB_POLLER_STATE_PATH = "./data/state.json"
            poller = GitLabPoller()
        assert "a/b" in poller.configured_projects
        assert "e/f" in poller.configured_projects
