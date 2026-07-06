import os
import re
from github import Github, GithubException, Auth
from dotenv import load_dotenv
from core.config import get_settings
from core.logger import get_logger

load_dotenv()
logger = get_logger("agents.github_tool")

class GitHubClient:
    def __init__(self, repo_name: str = None, installation_id: int = None):
        settings = get_settings()
        # Prefer explicit arg; only fall back to .env when nothing is supplied
        self.repo_name = repo_name or settings.GITHUB_REPO
        if not self.repo_name or self.repo_name == "owner/repository-name":
            raise ValueError("GITHUB_REPO is missing or not configured. Please set owner/repository-name in .env.")

        self._token = None
        self._auth_mode = None

        # Try GitHub App auth first (bot identity), fall back to PAT
        inst_id = installation_id or settings.GITHUB_APP_INSTALLATION_ID
        if settings.GITHUB_APP_ID and settings.GITHUB_APP_PRIVATE_KEY_PATH and inst_id:
            try:
                key_path = settings.GITHUB_APP_PRIVATE_KEY_PATH
                with open(key_path, "r") as f:
                    private_key = f.read()
                self._app_auth = Auth.AppAuth(settings.GITHUB_APP_ID, private_key)
                self._inst_auth = self._app_auth.get_installation_auth(inst_id)
                self.github = Github(auth=self._inst_auth)
                self._auth_mode = "app"
                self._installation_id = inst_id
                self._auth_mode = "app"
                logger.info(f"GitHub App authenticated (App ID: {settings.GITHUB_APP_ID})")
            except Exception as e:
                raise ValueError(f"GitHub App authentication failed: {e}. Check GITHUB_APP_ID, key path, and installation ID.")
        else:
            # Fallback: Personal Access Token
            token = settings.GITHUB_TOKEN or os.getenv("GITHUB_TOKEN")
            if not token or token == "your_github_personal_access_token_here":
                raise ValueError("GITHUB_TOKEN is missing or not configured. Please set a valid PAT in .env.")
            self._token = token
            self.github = Github(token)
            self._auth_mode = "pat"

        try:
            self.repo = self.github.get_repo(self.repo_name)
        except GithubException as e:
            if e.status == 404:
                raise ValueError(f"Repository {self.repo_name} not found. Check GITHUB_REPO in .env")
            raise

    def get_clone_token(self) -> str:
        """Get a string token suitable for git clone over HTTPS."""
        if self._auth_mode == "app":
            # the Auth.AppAuth wrapper manages the token for pygithub,
            # but to get the raw token for cloning we can use the installation auth
            return self._inst_auth.token
        return self._token

    def get_pr_diff(self, pr_number: int) -> str:
        try:
            pr = self.repo.get_pull(pr_number)
            files = pr.get_files()
            files_list = list(files)  # materialize so we can count

            settings = get_settings()
            max_total = settings.MAX_DIFF_SIZE
            max_per_file = max_total // max(len(files_list), 1)

            output = [f"PR #{pr_number}: {pr.title}\n\nChanged Files:\n"]
            for file in files_list:
                status = file.status
                additions = file.additions
                deletions = file.deletions
                patch = file.patch or "None"
                filename = file.filename

                # Truncate per-file to spread budget evenly
                if len(patch) > max_per_file:
                    patch = patch[:max_per_file] + f"\n... [truncated, {len(file.patch)} chars total]"

                output.append(f"FILE: {filename} ({status}) +{additions}/-{deletions}\nDIFF:\n{patch}\n---\n")

            full_output = "".join(output)
            # Final safety cap
            if len(full_output) > max_total:
                return full_output[:max_total] + f"\n... [Output truncated to {max_total} characters]"
            return full_output
        except GithubException as e:
            if e.status == 404:
                return f"Error: Pull request #{pr_number} not found."
            return f"Error fetching PR diff: {str(e)}"

    # Extensions to skip during review (binary, generated, non-source)
    SKIP_EXTENSIONS = {
        '.class', '.pyc', '.pyo', '.o', '.so', '.dll', '.exe',
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.webp',
        '.woff', '.woff2', '.ttf', '.eot',
        '.zip', '.tar', '.gz', '.jar', '.war',
        '.lock', '.map', '.min.js', '.min.css',
        '.pdf', '.doc', '.docx',
    }

    def get_reviewable_files(self, pr_number: int) -> list[dict]:
        """
        Return only files with reviewable source code patches.
        Filters out binary files, files with no patch, and non-source extensions.
        """
        try:
            pr = self.repo.get_pull(pr_number)
            result = []
            for file in pr.get_files():
                # Skip files with no patch (binary, deleted binary, etc.)
                if not file.patch:
                    continue
                # Skip non-source extensions
                ext = os.path.splitext(file.filename)[1].lower()
                if ext in self.SKIP_EXTENSIONS:
                    continue
                result.append({
                    "filename": file.filename,
                    "patch": file.patch,
                    "status": file.status,
                    "additions": file.additions,
                    "deletions": file.deletions,
                })
            return result
        except GithubException:
            return []

    def get_pr_files(self, pr_number: int) -> list[str]:
        try:
            pr = self.repo.get_pull(pr_number)
            return [file.filename for file in pr.get_files()]
        except GithubException:
            return []

    def get_valid_diff_lines(self, pr_number: int, file_path: str) -> list[int]:
        try:
            pr = self.repo.get_pull(pr_number)
            files = pr.get_files()
            for file in files:
                if file.filename == file_path:
                    lines = []
                    patch = file.patch or ""
                    current_line = -1
                    for line in patch.split('\n'):
                        if line.startswith('@@'):
                            match = re.search(r'\+([0-9]+)', line)
                            if match:
                                current_line = int(match.group(1))
                        elif line.startswith('+') and not line.startswith('+++'):
                            lines.append(current_line)
                            current_line += 1
                        elif line.startswith('-') and not line.startswith('---'):
                            pass
                        elif not line.startswith('\\'):
                            current_line += 1
                    return lines
            return []
        except Exception:
            return []

    def post_inline_comment(self, pr_number: int, commit_sha: str, file_path: str, line: int, body: str) -> bool:
        try:
            pr = self.repo.get_pull(pr_number)
            commit = self.repo.get_commit(commit_sha)
            # Add bot marker for identification
            marked_body = f"{body}\n<!-- devassist-ai -->"
            # Use keyword args — positional 4th arg is the deprecated 'position' param
            pr.create_review_comment(
                body=marked_body,
                commit=commit,
                path=file_path,
                line=line,
                side="RIGHT",
            )
            return True
        except Exception as e:
            logger.error(f"Error posting comment to PR #{pr_number} on {file_path}:{line}: {e}")
            return False

    def get_latest_commit_sha(self, pr_number: int) -> str:
        try:
            pr = self.repo.get_pull(pr_number)
            commits = pr.get_commits()
            return commits[commits.totalCount - 1].sha
        except Exception as e:
            logger.error(f"Error fetching latest commit for PR #{pr_number}: {e}")
            return ""

    # ─── New methods for incremental reviews ──────────────────────────────

    def get_diff_since_commit(self, pr_number: int, since_sha: str) -> str:
        """Get the diff of changes made AFTER since_sha (incremental review)."""
        try:
            pr = self.repo.get_pull(pr_number)
            comparison = self.repo.compare(since_sha, pr.head.sha)
            if not comparison.files:
                return ""

            output = [f"PR #{pr_number}: Incremental changes since {since_sha[:8]}\n\nChanged Files:\n"]
            for file in comparison.files:
                patch = file.patch or "None"
                output.append(f"FILE: {file.filename} ({file.status}) +{file.additions}/-{file.deletions}\nDIFF:\n{patch}\n---\n")

            full_output = "".join(output)
            settings = get_settings()
            max_size = settings.MAX_DIFF_SIZE
            if len(full_output) > max_size:
                return full_output[:max_size] + f"\n... [Truncated to {max_size} characters]"
            return full_output
        except Exception as e:
            logger.error(f"Error fetching incremental diff for PR #{pr_number}: {e}")
            return ""

    def post_general_comment(self, pr_number: int, body: str) -> bool:
        """Post a top-level summary comment on a PR (not inline)."""
        try:
            pr = self.repo.get_pull(pr_number)
            marked_body = f"{body}\n<!-- devassist-ai -->"
            pr.create_issue_comment(marked_body)
            return True
        except Exception as e:
            logger.error(f"Error posting summary comment to PR #{pr_number}: {e}")
            return False

    def comment_already_exists(self, pr_number: int, file_path: str, line: int, body_substring: str) -> bool:
        """Check if a similar bot comment already exists on this file+line (dedup)."""
        try:
            pr = self.repo.get_pull(pr_number)
            for comment in pr.get_review_comments():
                if ("<!-- devassist-ai -->" in (comment.body or "")
                        and comment.path == file_path
                        and getattr(comment, 'line', comment.position) == line
                        and body_substring in (comment.body or "")):
                    return True
            return False
        except Exception:
            return False

    def get_existing_bot_comments(self, pr_number: int) -> list:
        """Fetch all bot comments (containing our marker) on a PR."""
        try:
            pr = self.repo.get_pull(pr_number)
            return [
                {"id": c.id, "body": c.body, "path": c.path, "line": getattr(c, 'line', c.position)}
                for c in pr.get_review_comments()
                if "<!-- devassist-ai -->" in (c.body or "")
            ]
        except Exception:
            return []

    def reply_to_comment(self, pr_number: int, comment_id: int, body: str) -> bool:
        """Reply to a specific review comment (conversation threading)."""
        try:
            pr = self.repo.get_pull(pr_number)
            marked_body = f"{body}\n<!-- devassist-ai -->"
            pr.create_review_comment_reply(comment_id, marked_body)
            return True
        except Exception as e:
            logger.error(f"Error replying to comment {comment_id}: {e}")
            return False

    def get_comment_context(self, comment_id: int) -> dict:
        """Get the context of a comment (body + file + line)."""
        try:
            comment = self.repo.get_pull_review_comment(comment_id)
            return {
                "id": comment.id,
                "body": comment.body,
                "path": comment.path,
                "line": comment.position,
                "diff_hunk": comment.diff_hunk,
                "user": comment.user.login,
                "is_bot": "<!-- devassist-ai -->" in (comment.body or ""),
            }
        except Exception:
            return {}


_github_client_instance = None
_github_client_key: tuple = (None, None)  # (repo_name, installation_id)

def get_github_client(repo_name: str = None, installation_id: int = None) -> GitHubClient:
    """Return a GitHubClient, refreshing the singleton when repo or installation changes."""
    global _github_client_instance, _github_client_key
    settings = get_settings()
    # Resolve the effective repo name so we can key correctly
    effective_repo = repo_name or settings.GITHUB_REPO
    cache_key = (effective_repo, installation_id)
    if _github_client_instance is None or _github_client_key != cache_key:
        _github_client_instance = GitHubClient(repo_name, installation_id=installation_id)
        _github_client_key = cache_key
    return _github_client_instance
