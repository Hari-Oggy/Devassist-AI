"""
GitLab REST API Client — DevAssist-AI Phase 5.

Separate from GitHub client (api/webhook.py + api/poller.py) so both
integrations are independently maintainable.

Supports:
    - Fetching merge request diffs
    - Posting review comments (discussions) on MRs
    - Listing open MRs for a project
    - Getting project metadata

Authentication:
    Uses a GitLab Personal Access Token (PAT) or Project Access Token
    via the GITLAB_TOKEN environment variable.

Base URL:
    Defaults to https://gitlab.com/api/v4 but supports self-hosted instances
    via GITLAB_API_URL environment variable.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from core.config import get_settings
from core.logger import get_logger

logger = get_logger("providers.gitlab_client")

# GitLab API paginates at 20 items by default; we use 100
_PER_PAGE = 100


class GitLabClient:
    """Async GitLab REST API client.

    Wraps the GitLab v4 API with typed methods for merge request operations.
    Uses httpx.AsyncClient for connection pooling.

    Example::

        async with GitLabClient() as client:
            mr = await client.get_merge_request("my-group/my-repo", 42)
            diff = await client.get_mr_diff("my-group/my-repo", 42)
            await client.post_mr_comment("my-group/my-repo", 42, "Looks good!")
    """

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        settings = get_settings()
        self._token = token or getattr(settings, "GITLAB_TOKEN", None) or ""
        self._base_url = (
            base_url
            or getattr(settings, "GITLAB_API_URL", None)
            or "https://gitlab.com/api/v4"
        ).rstrip("/")
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    # ── Context manager ────────────────────────────────────────────────

    async def __aenter__(self) -> "GitLabClient":
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "PRIVATE-TOKEN": self._token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── Project / MR metadata ──────────────────────────────────────────

    async def get_project(self, project_path: str) -> dict:
        """Fetch project metadata by path (e.g. 'group/repo').

        Args:
            project_path: URL-encoded project path or numeric project ID.

        Returns:
            Dict with project id, name, default_branch, web_url, etc.
        """
        encoded = _encode_path(project_path)
        return await self._get(f"/projects/{encoded}")

    async def list_open_mrs(
        self,
        project_path: str,
        target_branch: Optional[str] = None,
        per_page: int = _PER_PAGE,
    ) -> list[dict]:
        """List open merge requests for a project.

        Args:
            project_path: Project path or numeric ID.
            target_branch: Optional filter for target branch.
            per_page: Page size (max 100).

        Returns:
            List of MR metadata dicts.
        """
        encoded = _encode_path(project_path)
        params: dict[str, Any] = {
            "state": "opened",
            "per_page": per_page,
            "order_by": "updated_at",
            "sort": "desc",
        }
        if target_branch:
            params["target_branch"] = target_branch

        return await self._get(f"/projects/{encoded}/merge_requests", params=params)

    async def get_merge_request(self, project_path: str, mr_iid: int) -> dict:
        """Fetch a single merge request by internal ID.

        Args:
            project_path: Project path or numeric ID.
            mr_iid: MR internal IID (shown in the GitLab UI, e.g. !42 → 42).

        Returns:
            Full MR metadata dict.
        """
        encoded = _encode_path(project_path)
        return await self._get(f"/projects/{encoded}/merge_requests/{mr_iid}")

    async def get_mr_diff(self, project_path: str, mr_iid: int) -> list[dict]:
        """Fetch the raw diffs for all changed files in a merge request.

        Args:
            project_path: Project path or numeric ID.
            mr_iid: MR internal IID.

        Returns:
            List of dicts with keys: old_path, new_path, diff, new_file,
            renamed_file, deleted_file, a_mode, b_mode.
        """
        encoded = _encode_path(project_path)
        data = await self._get(
            f"/projects/{encoded}/merge_requests/{mr_iid}/diffs"
        )
        # Normalise to list
        if isinstance(data, dict):
            return data.get("diffs", [])
        return data if isinstance(data, list) else []

    async def get_mr_diff_as_text(self, project_path: str, mr_iid: int) -> str:
        """Return all file diffs concatenated as a unified diff string.

        Args:
            project_path: Project path or numeric ID.
            mr_iid: MR internal IID.

        Returns:
            Unified diff string suitable for LLM input.
        """
        diffs = await self.get_mr_diff(project_path, mr_iid)
        parts: list[str] = []
        for d in diffs:
            old_path = d.get("old_path", "")
            new_path = d.get("new_path", "")
            diff_text = d.get("diff", "")
            if diff_text:
                header = f"--- a/{old_path}\n+++ b/{new_path}\n"
                parts.append(header + diff_text)
        return "\n".join(parts)

    # ── Comment posting ────────────────────────────────────────────────

    async def post_mr_comment(
        self,
        project_path: str,
        mr_iid: int,
        body: str,
    ) -> dict:
        """Post a general comment on a merge request.

        Args:
            project_path: Project path or numeric ID.
            mr_iid: MR internal IID.
            body: Markdown comment text.

        Returns:
            Created note metadata dict.
        """
        encoded = _encode_path(project_path)
        return await self._post(
            f"/projects/{encoded}/merge_requests/{mr_iid}/notes",
            json={"body": body},
        )

    async def post_mr_inline_comment(
        self,
        project_path: str,
        mr_iid: int,
        body: str,
        file_path: str,
        line: int,
        base_sha: str,
        head_sha: str,
        start_sha: str,
    ) -> dict:
        """Post an inline diff comment on a specific file and line.

        Args:
            project_path: Project path or numeric ID.
            mr_iid: MR internal IID.
            body: Comment text.
            file_path: File path in the new version of the code.
            line: Line number to comment on (in new file).
            base_sha / head_sha / start_sha: SHAs for diff position calculation.

        Returns:
            Created discussion metadata dict.
        """
        encoded = _encode_path(project_path)
        position = {
            "base_sha": base_sha,
            "head_sha": head_sha,
            "start_sha": start_sha,
            "position_type": "text",
            "new_path": file_path,
            "new_line": line,
        }
        return await self._post(
            f"/projects/{encoded}/merge_requests/{mr_iid}/discussions",
            json={"body": body, "position": position},
        )

    async def get_mr_commits(self, project_path: str, mr_iid: int) -> list[dict]:
        """Return the list of commits in a merge request.

        Args:
            project_path: Project path or numeric ID.
            mr_iid: MR internal IID.

        Returns:
            List of commit dicts with id, title, author_name, created_at.
        """
        encoded = _encode_path(project_path)
        return await self._get(
            f"/projects/{encoded}/merge_requests/{mr_iid}/commits"
        )

    # ── Private HTTP helpers ───────────────────────────────────────────

    async def _get(self, path: str, params: Optional[dict] = None) -> Any:
        resp = await self._request("GET", path, params=params)
        return resp

    async def _post(self, path: str, json: Optional[dict] = None) -> Any:
        resp = await self._request("POST", path, json=json)
        return resp

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
        retries: int = 3,
    ) -> Any:
        if self._client is None:
            raise RuntimeError(
                "GitLabClient must be used as an async context manager."
            )

        last_exc: Exception = RuntimeError("No request made")
        for attempt in range(1, retries + 1):
            try:
                response = await self._client.request(
                    method, path, params=params, json=json
                )

                if response.status_code == 429:
                    wait = int(response.headers.get("Retry-After", "5"))
                    logger.warning("GitLab rate limited — waiting %ds", wait)
                    await asyncio.sleep(wait)
                    continue

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as exc:
                logger.error(
                    "GitLab API error [attempt %d/%d]: %s %s → %d",
                    attempt, retries, method, path, exc.response.status_code,
                )
                last_exc = exc
                if exc.response.status_code < 500:
                    raise  # Don't retry 4xx
                await asyncio.sleep(2 ** attempt)

            except httpx.RequestError as exc:
                logger.error(
                    "GitLab request error [attempt %d/%d]: %s",
                    attempt, retries, exc,
                )
                last_exc = exc
                await asyncio.sleep(2 ** attempt)

        raise last_exc


def _encode_path(project_path: str) -> str:
    """URL-encode a GitLab project path for API use.

    GitLab requires '/' → '%2F' in path segments.

    Args:
        project_path: e.g. 'my-group/my-repo' or numeric '12345'.

    Returns:
        URL-encoded string safe for use in URL path segments.
    """
    from urllib.parse import quote
    return quote(str(project_path), safe="")
