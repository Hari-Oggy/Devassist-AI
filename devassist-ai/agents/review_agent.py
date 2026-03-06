"""
PR Review Agent — uses the LLM Router (never provider APIs directly).
"""

import json
import re
from datetime import datetime

from core.config import get_settings
from core.logger import get_logger, generate_request_id
from core.review_state import (
    get_last_reviewed_sha,
    save_reviewed_sha,
)
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

    # ─── Incremental Review ───────────────────────────────────────────────

    def review_pr_incremental(self, pr_number: int) -> dict:
        """
        Smart incremental review:
          - First review: full diff
          - Subsequent reviews: only changes since last reviewed commit
          - Posts a summary comment + deduped inline comments
          - Saves the reviewed SHA for next time
        """
        self.audit_log = []
        request_id = generate_request_id()
        self._log(f"[{request_id}] Starting incremental review for PR #{pr_number}")

        # 1. Determine if this is a first review or incremental
        last_sha = get_last_reviewed_sha(pr_number)
        is_incremental = bool(last_sha)

        if is_incremental:
            self._log(f"Incremental mode: changes since {last_sha[:8]}")
            diff = self.github_client.get_diff_since_commit(pr_number, last_sha)
            if not diff:
                self._log("No new changes since last review — skipping")
                return {"pr_number": pr_number, "success": True, "comments": [],
                        "audit_log": self.audit_log, "message": "No new changes"}
        else:
            self._log("First review: full diff")
            diff = self.github_client.get_pr_diff(pr_number)

        if not diff or diff.startswith("Error"):
            self._log(f"Failed to fetch diff: {diff}")
            return {"pr_number": pr_number, "success": False, "error": diff or "Empty diff",
                    "comments": [], "audit_log": self.audit_log}

        # 2. Enforce max diff size
        max_size = self.settings.MAX_DIFF_SIZE
        if len(diff) > max_size:
            self._log(f"Diff truncated: {len(diff)} → {max_size} chars")
            diff = diff[:max_size] + f"\n... [Truncated to {max_size} characters]"

        changed_files = self.github_client.get_pr_files(pr_number)
        self._log(f"Found {len(changed_files)} changed files")

        # 3. Gather codebase context via RAG
        context = ""
        try:
            context = self.retriever.get_context("code review patterns and conventions", k=3)
            self._log("Fetched codebase context via RAG")
        except Exception as e:
            self._log(f"RAG context unavailable: {e}")

        # 4. Run linter on changed .py files
        lint_results = ""
        for f in changed_files:
            if f.endswith(".py"):
                try:
                    result = pylint_analysis.invoke(f)
                    if result and "No issues found" not in result:
                        lint_results += f"\n{result}\n"
                except Exception:
                    pass

        # 5. Build LLM request
        system_prompt = load_prompt("review_prompt")
        review_type = "incremental changes" if is_incremental else "full PR diff"
        user_content = f"Review this {review_type} and provide inline comments:\n\n{diff}"
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

        # 6. Call the Router
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

        self._log(f"Response from {llm_response.provider}/{llm_response.model} "
                   f"({llm_response.tokens_input}+{llm_response.tokens_output} tokens, {llm_response.latency:.1f}s)")

        # 7. Parse comments
        parsed_comments, parse_error = self._parse_comments(llm_response.content)
        if parse_error:
            self._log("Warning: Could not parse JSON comments from LLM output")

        # 8. Post inline comments with dedup
        commit_sha = self.github_client.get_latest_commit_sha(pr_number)
        posted = []
        skipped_dedup = 0
        for comment in parsed_comments:
            file_path = comment.get("file")
            line = comment.get("line")
            severity = comment.get("severity", "suggestion").upper()
            body = f"**[{severity}]** {comment.get('comment')}"

            # Dedup: skip if identical comment already exists
            if self.github_client.comment_already_exists(pr_number, file_path, line, comment.get("comment", "")[:50]):
                skipped_dedup += 1
                self._log(f"Dedup: skipped {file_path}:{line} (already exists)")
                continue

            valid_lines = self.github_client.get_valid_diff_lines(pr_number, file_path)
            if line in valid_lines:
                success = self.github_client.post_inline_comment(pr_number, commit_sha, file_path, line, body)
                if success:
                    posted.append(comment)
                    self._log(f"Posted comment on {file_path}:{line}")
            else:
                self._log(f"Skipped {file_path}:{line} (not in diff)")

        if skipped_dedup:
            self._log(f"Dedup: {skipped_dedup} duplicate comments skipped")

        # 9. Post summary comment
        summary = self._build_summary(
            pr_number=pr_number,
            is_incremental=is_incremental,
            parsed_comments=parsed_comments,
            posted_comments=posted,
            changed_files=changed_files,
            model=f"{llm_response.provider}/{llm_response.model}",
            tokens=f"{llm_response.tokens_input}+{llm_response.tokens_output}",
        )
        self.github_client.post_general_comment(pr_number, summary)
        self._log("Posted summary comment")

        # 10. Save reviewed SHA
        new_sha = self.github_client.get_latest_commit_sha(pr_number)
        if new_sha:
            save_reviewed_sha(pr_number, new_sha)

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
            "incremental": is_incremental,
        }

    # ─── Helpers ──────────────────────────────────────────────────────────

    def _build_summary(self, pr_number, is_incremental, parsed_comments,
                       posted_comments, changed_files, model, tokens) -> str:
        """Build a CodeRabbit-style summary comment."""
        review_type = "🔄 Incremental Review" if is_incremental else "📋 Full Review"
        severity_counts = {}
        for c in parsed_comments:
            s = c.get("severity", "suggestion").lower()
            severity_counts[s] = severity_counts.get(s, 0) + 1

        severity_line = " | ".join(f"**{k.title()}**: {v}" for k, v in severity_counts.items()) or "No issues found"

        lines = [
            f"## 🤖 DevAssist AI — {review_type}",
            "",
            f"**Files reviewed**: {len(changed_files)} | "
            f"**Comments**: {len(posted_comments)}/{len(parsed_comments)} posted | "
            f"**Model**: `{model}`",
            "",
            f"### Findings",
            severity_line,
            "",
        ]

        # Add a brief for each finding
        if parsed_comments:
            lines.append("| File | Line | Severity | Issue |")
            lines.append("|------|------|----------|-------|")
            for c in parsed_comments[:15]:  # Cap at 15 rows
                lines.append(
                    f"| `{c.get('file', '?')}` | {c.get('line', '?')} | "
                    f"{c.get('severity', 'suggestion')} | {c.get('comment', '')[:80]} |"
                )
            if len(parsed_comments) > 15:
                lines.append(f"| ... | ... | ... | +{len(parsed_comments) - 15} more (see inline comments) |")

        lines.append("")
        lines.append(f"*Reviewed with `{model}` ({tokens} tokens)*")
        return "\n".join(lines)

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
