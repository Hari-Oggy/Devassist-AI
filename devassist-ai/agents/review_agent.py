"""
PR Review Agent — uses the LLM Router (never provider APIs directly).
"""

import json
import re
from datetime import datetime

from core.config import get_settings
from core.logger import get_logger, generate_request_id
from llm.router import LLMRouter
from llm.schemas import LLMRequest
from prompts import load_prompt
from rag.retriever import CodebaseRetriever
from agents.tools.github_tool import get_github_client
from agents.tools.linter_tool import pylint_analysis

logger = get_logger("agents.review")


class ReviewAgent:
    def __init__(self):
        self.settings = get_settings()
        self.router = LLMRouter()
        self.retriever = CodebaseRetriever()
        self.github_client = get_github_client()
        self.audit_log: list[str] = []

    def review_pr(self, pr_number: int) -> dict:
        """Full PR review pipeline: fetch diff → gather context → call LLM → post comments."""
        self.audit_log = []
        request_id = generate_request_id()
        self._log(f"[{request_id}] Starting review for PR #{pr_number}")

        # 1. Fetch PR diff
        diff = self.github_client.get_pr_diff(pr_number)
        if diff.startswith("Error"):
            self._log(f"Failed to fetch diff: {diff}")
            return {"pr_number": pr_number, "success": False, "error": diff, "comments": [], "audit_log": self.audit_log}

        changed_files = self.github_client.get_pr_files(pr_number)
        self._log(f"Found {len(changed_files)} changed files")

        # 2. Gather codebase context via RAG
        context = ""
        try:
            context = self.retriever.get_context("code review patterns and conventions", k=3)
            self._log("Fetched codebase context via RAG")
        except Exception as e:
            self._log(f"RAG context unavailable: {e}")

        # 3. Run linter on changed .py files (best-effort)
        lint_results = ""
        for f in changed_files:
            if f.endswith(".py"):
                try:
                    result = pylint_analysis.invoke(f)
                    if result and "No issues found" not in result:
                        lint_results += f"\n{result}\n"
                except Exception:
                    pass

        # 4. Build LLM request
        system_prompt = load_prompt("review_prompt")
        user_content = f"Review this PR diff and provide inline comments:\n\n{diff}"
        if context:
            user_content += f"\n\n--- Codebase Context ---\n{context}"
        if lint_results:
            user_content += f"\n\n--- Linter Results ---\n{lint_results}"

        llm_request = LLMRequest(
            task_type="code_review",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=self.settings.REVIEW_TEMPERATURE,
            metadata={"request_id": request_id, "pr_number": pr_number},
        )

        # 5. Call the Router
        self._log("Sending to LLM Router...")
        llm_response = self.router.generate(llm_request)

        if not llm_response.success:
            self._log(f"LLM call failed: {llm_response.error}")
            return {
                "pr_number": pr_number, "success": False,
                "error": llm_response.error, "comments": [],
                "audit_log": self.audit_log,
                "model_used": llm_response.model,
                "provider_used": llm_response.provider,
            }

        self._log(f"Response received from {llm_response.provider}/{llm_response.model} "
                   f"({llm_response.tokens_input}+{llm_response.tokens_output} tokens, {llm_response.latency:.1f}s)")

        # 6. Parse comments from LLM output
        parsed_comments, parse_error = self._parse_comments(llm_response.content)
        if parse_error:
            self._log("Warning: Could not parse JSON comments from LLM output")

        # 7. Post inline comments on GitHub
        commit_sha = self.github_client.get_latest_commit_sha(pr_number)
        posted = []
        for comment in parsed_comments:
            file_path = comment.get("file")
            line = comment.get("line")
            body = f"**[{comment.get('severity', 'suggestion').upper()}]** {comment.get('comment')}"

            valid_lines = self.github_client.get_valid_diff_lines(pr_number, file_path)
            if line in valid_lines:
                success = self.github_client.post_inline_comment(pr_number, commit_sha, file_path, line, body)
                if success:
                    posted.append(comment)
                    self._log(f"Posted comment on {file_path}:{line}")
            else:
                self._log(f"Skipped {file_path}:{line} (not in diff)")

        self._log(f"Review complete. {len(posted)}/{len(parsed_comments)} comments posted.")
        return {
            "pr_number": pr_number,
            "comments": posted,
            "files_reviewed": changed_files,
            "audit_log": self.audit_log,
            "model_used": llm_response.model,
            "provider_used": llm_response.provider,
            "fallback_used": llm_response.fallback_used,
            "success": True,
        }

    def _parse_comments(self, output: str) -> tuple[list, bool]:
        match = re.search(r'\[\s*\{.*?\}\s*\]', output, re.DOTALL)
        if not match:
            return [], True
        try:
            comments = json.loads(match.group(0))
            return [c for c in comments if all(k in c for k in ["file", "line", "comment"])], False
        except json.JSONDecodeError:
            return [], True

    def _log(self, message: str):
        entry = f"[{datetime.now().isoformat()}] {message}"
        self.audit_log.append(entry)
        logger.info(message)
