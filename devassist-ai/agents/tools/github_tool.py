import os
from github import Github, GithubException
from dotenv import load_dotenv

load_dotenv()

class GitHubClient:
    def __init__(self):
        token = os.getenv("GITHUB_TOKEN")
        if not token or token == "your_github_personal_access_token_here":
            raise ValueError("GITHUB_TOKEN is missing or not configured. Please set a valid PAT in .env.")
            
        repo_name = os.getenv("GITHUB_REPO")
        if not repo_name or repo_name == "owner/repository-name":
            raise ValueError("GITHUB_REPO is missing or not configured. Please set owner/repository-name in .env.")
            
        self.github = Github(token)
        try:
            self.repo = self.github.get_repo(repo_name)
        except GithubException as e:
            if e.status == 404:
                raise ValueError(f"Repository {repo_name} not found. Check GITHUB_REPO in .env")
            raise

    def get_pr_diff(self, pr_number: int) -> str:
        try:
            pr = self.repo.get_pull(pr_number)
            files = pr.get_files()
            
            output = [f"PR #{pr_number}: {pr.title}\n\nChanged Files:\n"]
            for file in files:
                status = file.status
                additions = file.additions
                deletions = file.deletions
                patch = file.patch or "None"
                filename = file.filename
                
                output.append(f"FILE: {filename} ({status}) +{additions}/-{deletions}\nDIFF:\n{patch}\n---\n")
            
            full_output = "".join(output)
            if len(full_output) > 8000:
                return full_output[:8000] + "\n... [Output truncated to 8000 characters]"
            return full_output
        except GithubException as e:
            if e.status == 404:
                return f"Error: Pull request #{pr_number} not found."
            return f"Error fetching PR diff: {str(e)}"

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
                            import re
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
            pr.create_review_comment(body, commit, file_path, line)
            return True
        except Exception as e:
            print(f"Error posting comment to PR #{pr_number} on {file_path}:{line}: {e}")
            return False

    def get_latest_commit_sha(self, pr_number: int) -> str:
        try:
            pr = self.repo.get_pull(pr_number)
            commits = pr.get_commits()
            return commits[commits.totalCount - 1].sha
        except Exception as e:
            print(f"Error fetching latest commit for PR #{pr_number}: {e}")
            return ""

_github_client_instance = None

def get_github_client() -> GitHubClient:
    global _github_client_instance
    if _github_client_instance is None:
        _github_client_instance = GitHubClient()
    return _github_client_instance
