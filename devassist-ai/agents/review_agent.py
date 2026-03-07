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
        """Full PR review pipeline: fetch files → review each file individually → post comments."""
        self.audit_log = []
        request_id = generate_request_id()
        self._log(f"[{request_id}] Starting review for PR #{pr_number}")

        # 1. Fetch reviewable files (filters out binary, .class, etc.)
        reviewable_files = self.github_client.get_reviewable_files(pr_number)
        all_changed_files = self.github_client.get_pr_files(pr_number)
        self._log(f"Found {len(all_changed_files)} changed files, {len(reviewable_files)} reviewable")

        if not reviewable_files:
            self._log("No reviewable source files found in this PR")
            return {
                "pr_number": pr_number, "success": True,
                "comments": [], "files_reviewed": all_changed_files,
                "audit_log": self.audit_log,
                "model_used": "", "provider_used": "",
            }

        # 2. Gather codebase context via RAG (once for the whole PR)
        context = ""
        try:
            context = self.retriever.get_context("code review patterns and conventions", k=3)
            self._log("Fetched codebase context via RAG")
        except Exception as e:
            self._log(f"RAG context unavailable: {e}")

        # 3. Select system prompt based on provider
        if self.settings.LLM_PROVIDER == "local":
            system_prompt = load_prompt("review_prompt_local")
        else:
            system_prompt = load_prompt("review_prompt")

        # 4. Review each file individually (per-file architecture)
        all_parsed_comments = []
        last_response = None

        for file_data in reviewable_files:
            filename = file_data["filename"]
            patch = file_data["patch"]
            self._log(f"Reviewing {filename} ({file_data['additions']}+/{file_data['deletions']}-) ...")

            # Build focused prompt for this single file
            user_content = (
                f"Review the changes in this file and provide inline comments:\n\n"
                f"File: {filename}\n"
                f"Status: {file_data['status']}\n\n"
                f"{patch}"
            )
            if context:
                user_content += f"\n\n--- Codebase Context ---\n{context}"

            # Run linter for .py files
            if filename.endswith(".py"):
                try:
                    lint_result = pylint_analysis.invoke(filename)
                    if lint_result and "No issues found" not in lint_result:
                        user_content += f"\n\n--- Linter Results ---\n{lint_result}"
                except Exception:
                    pass

            llm_request = LLMRequest(
                task_type="code_review",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=self.settings.REVIEW_TEMPERATURE,
                metadata={"request_id": request_id, "pr_number": pr_number, "file": filename},
            )

            llm_response = self.router.generate(llm_request)
            last_response = llm_response

            if not llm_response.success:
                self._log(f"  LLM call failed for {filename}: {llm_response.error}")
                continue

            self._log(f"  Response: {llm_response.provider}/{llm_response.model} "
                       f"({llm_response.tokens_input}+{llm_response.tokens_output} tokens, {llm_response.latency:.1f}s)")

            # Parse comments from this file's review
            parsed_comments, parse_error = self._parse_comments(llm_response.content)
            if parse_error:
                self._log(f"  Warning: Could not parse JSON comments for {filename}")
            else:
                # Ensure file path is set correctly on each comment
                for c in parsed_comments:
                    c["file"] = filename
                all_parsed_comments.extend(parsed_comments)
                self._log(f"  Found {len(parsed_comments)} comment(s)")

        # 5. Post all collected comments to GitHub
        commit_sha = self.github_client.get_latest_commit_sha(pr_number)
        posted = []
        for comment in all_parsed_comments:
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
                self._log(f"Skipped {file_path}:{line} (not in diff hunk)")

        self._log(f"Review complete. {len(posted)}/{len(all_parsed_comments)} comments posted across {len(reviewable_files)} files.")
        return {
            "pr_number": pr_number,
            "comments": posted,
            "files_reviewed": [f["filename"] for f in reviewable_files],
            "audit_log": self.audit_log,
            "model_used": last_response.model if last_response else "",
            "provider_used": last_response.provider if last_response else "",
            "fallback_used": last_response.fallback_used if last_response else False,
            "success": True,
        }

    # ─── Incremental Review ───────────────────────────────────────────────

    def review_pr_incremental(self, pr_number: int) -> dict:
        """
        Smart incremental review with per-file architecture:
          - First review: uses get_reviewable_files (per-file)
          - Subsequent reviews: only changes since last reviewed commit (per-file)
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
            # For incremental, get changed files since last review
            try:
                pr = self.github_client.repo.get_pull(pr_number)
                comparison = self.github_client.repo.compare(last_sha, pr.head.sha)
                if not comparison.files:
                    self._log("No new changes since last review — skipping")
                    return {"pr_number": pr_number, "success": True, "comments": [],
                            "audit_log": self.audit_log, "message": "No new changes"}

                reviewable_files = []
                for file in comparison.files:
                    if not file.patch:
                        continue
                    import os as _os
                    ext = _os.path.splitext(file.filename)[1].lower()
                    if ext in self.github_client.SKIP_EXTENSIONS:
                        continue
                    reviewable_files.append({
                        "filename": file.filename,
                        "patch": file.patch,
                        "status": file.status,
                        "additions": file.additions,
                        "deletions": file.deletions,
                    })
            except Exception as e:
                self._log(f"Failed to fetch incremental diff: {e}")
                return {"pr_number": pr_number, "success": False, "error": str(e),
                        "comments": [], "audit_log": self.audit_log}
        else:
            self._log("First review: full diff (per-file)")
            reviewable_files = self.github_client.get_reviewable_files(pr_number)

        all_changed_files = self.github_client.get_pr_files(pr_number)
        self._log(f"Found {len(all_changed_files)} changed files, {len(reviewable_files)} reviewable")

        if not reviewable_files:
            self._log("No reviewable source files found")
            return {"pr_number": pr_number, "success": True, "comments": [],
                    "files_reviewed": all_changed_files, "audit_log": self.audit_log,
                    "model_used": "", "provider_used": "", "incremental": is_incremental}

        # 2. Gather codebase context via RAG (once)
        context = ""
        try:
            context = self.retriever.get_context("code review patterns and conventions", k=3)
            self._log("Fetched codebase context via RAG")
        except Exception as e:
            self._log(f"RAG context unavailable: {e}")

        # 3. Select system prompt
        if self.settings.LLM_PROVIDER == "local":
            system_prompt = load_prompt("review_prompt_local")
        else:
            system_prompt = load_prompt("review_prompt")

        # 4. Review each file individually (per-file architecture)
        all_parsed_comments = []
        last_response = None
        review_type = "incremental changes" if is_incremental else "full PR"

        for file_data in reviewable_files:
            filename = file_data["filename"]
            patch = file_data["patch"]
            self._log(f"Reviewing {filename} ({file_data['additions']}+/{file_data['deletions']}-) ...")

            user_content = (
                f"Review the {review_type} in this file and provide inline comments:\n\n"
                f"File: {filename}\n"
                f"Status: {file_data['status']}\n\n"
                f"{patch}"
            )
            if context:
                user_content += f"\n\n--- Codebase Context ---\n{context}"

            # Run linter for .py files
            if filename.endswith(".py"):
                try:
                    lint_result = pylint_analysis.invoke(filename)
                    if lint_result and "No issues found" not in lint_result:
                        user_content += f"\n\n--- Linter Results ---\n{lint_result}"
                except Exception:
                    pass

            llm_request = LLMRequest(
                task_type="code_review",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=self.settings.REVIEW_TEMPERATURE,
                metadata={"request_id": request_id, "pr_number": pr_number, "file": filename},
            )

            llm_response = self.router.generate(llm_request)
            last_response = llm_response

            if not llm_response.success:
                self._log(f"  LLM call failed for {filename}: {llm_response.error}")
                continue

            self._log(f"  Response: {llm_response.provider}/{llm_response.model} "
                       f"({llm_response.tokens_input}+{llm_response.tokens_output} tokens, {llm_response.latency:.1f}s)")

            parsed_comments, parse_error = self._parse_comments(llm_response.content)
            if parse_error:
                self._log(f"  Warning: Could not parse JSON comments for {filename}")
            else:
                for c in parsed_comments:
                    c["file"] = filename
                all_parsed_comments.extend(parsed_comments)
                self._log(f"  Found {len(parsed_comments)} comment(s)")

        # 5. Post inline comments with dedup
        commit_sha = self.github_client.get_latest_commit_sha(pr_number)
        posted = []
        skipped_dedup = 0
        for comment in all_parsed_comments:
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
                self._log(f"Skipped {file_path}:{line} (not in diff hunk)")

        if skipped_dedup:
            self._log(f"Dedup: {skipped_dedup} duplicate comments skipped")

        # 6. Post summary comment
        total_tokens = f"{last_response.tokens_input}+{last_response.tokens_output}" if last_response else "0+0"
        model_name = f"{last_response.provider}/{last_response.model}" if last_response else "N/A"
        summary = self._build_summary(
            pr_number=pr_number,
            is_incremental=is_incremental,
            parsed_comments=all_parsed_comments,
            posted_comments=posted,
            changed_files=[f["filename"] for f in reviewable_files],
            model=model_name,
            tokens=total_tokens,
        )
        self.github_client.post_general_comment(pr_number, summary)
        self._log("Posted summary comment")

        # 7. Save reviewed SHA
        new_sha = self.github_client.get_latest_commit_sha(pr_number)
        if new_sha:
            save_reviewed_sha(pr_number, new_sha)

        self._log(f"Review complete. {len(posted)}/{len(all_parsed_comments)} comments posted across {len(reviewable_files)} files.")
        return {
            "pr_number": pr_number,
            "comments": posted,
            "files_reviewed": [f["filename"] for f in reviewable_files],
            "audit_log": self.audit_log,
            "model_used": last_response.model if last_response else "",
            "provider_used": last_response.provider if last_response else "",
            "fallback_used": last_response.fallback_used if last_response else False,
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
        # Strip markdown code fences that local models add (```json ... ```)
        cleaned = re.sub(r'```(?:json)?\s*', '', output)
        cleaned = re.sub(r'```\s*$', '', cleaned.strip())
        match = re.search(r'\[\s*\{.*?\}\s*\]', cleaned, re.DOTALL)
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
