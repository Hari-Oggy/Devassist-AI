"""Quick verification of get_reviewable_files and per-file review."""
from agents.tools.github_tool import GitHubClient

gh = GitHubClient()
print(f"Auth mode: {gh._auth_mode}")

files = gh.get_reviewable_files(2)
print(f"Reviewable files: {len(files)}")
for f in files:
    print(f"  {f['filename']} ({f['status']}, {len(f['patch'])} chars)")
