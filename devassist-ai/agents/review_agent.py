"""
PR Review Agent — uses the LLM Router (never provider APIs directly).
"""

import json
import os
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

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
from agents.tools.linter_tool import run_linter

logger = get_logger("agents.review")


class ReviewAgent:
    def __init__(self):
        self.settings = get_settings()
        self.router = LLMRouter()
        self.retriever = CodebaseRetriever()
        self.github_client = get_github_client()
        self.audit_log: list[str] = []

    # ─── Per-File Review Helper (used by both review_pr and review_pr_incremental) ─

    def _review_single_file(self, file_data: dict, system_prompt: str, context: str,
                            request_id: str, pr_number: int, review_type: str = "full PR") -> dict:
        """
        Review a single file and return parsed comments + metadata.
        Thread-safe: does not mutate shared state (audit_log is appended after).
        """
        filename = file_data["filename"]
        patch = file_data["patch"]

        # Build focused prompt to exactly match pre-P2 behavior
        if review_type == "full PR":
            prefix = "Review the changes in this file"
        else:
            prefix = f"Review the {review_type} in this file"

        user_content = (
            f"{prefix} and provide inline comments:\n\n"
            f"File: {filename}\n"
            f"Status: {file_data['status']}\n\n"
            f"{patch}"
        )
        if context:
            user_content += f"\n\n--- Codebase Context ---\n{context}"

        # Run linter (auto-selects by extension: pylint, eslint, checkstyle)
        lint_result = run_linter(filename)
        if lint_result:
            user_content += f"\n\n--- Linter Results ---\n{lint_result}"

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

        result = {
            "filename": filename,
            "additions": file_data["additions"],
            "deletions": file_data["deletions"],
            "response": llm_response,
            "comments": [],
            "logs": [],
        }

        result["logs"].append(
            f"Reviewing {filename} ({file_data['additions']}+/{file_data['deletions']}-) ..."
        )

        if not llm_response.success:
            result["logs"].append(f"  LLM call failed for {filename}: {llm_response.error}")
            return result

        result["logs"].append(
            f"  Response: {llm_response.provider}/{llm_response.model} "
            f"({llm_response.tokens_input}+{llm_response.tokens_output} tokens, {llm_response.latency:.1f}s)"
        )

        parsed_comments, parse_error = self._parse_comments(llm_response.content)
        if parse_error:
            result["logs"].append(f"  Warning: Could not parse JSON comments for {filename}")
        else:
            for c in parsed_comments:
                c["file"] = filename
            result["comments"] = parsed_comments
            result["logs"].append(f"  Found {len(parsed_comments)} comment(s)")

        return result

    def _get_max_workers(self) -> int:
        """Determine thread pool size based on LLM provider."""
        if self.settings.LLM_PROVIDER == "local":
            return 1  # Local LLMs can't handle concurrent requests
        return 3  # Cloud APIs support parallel calls

    # ─── Shared Helpers (eliminates duplication between review_pr / review_pr_incremental) ─

    def _prepare_review(self) -> tuple[str, str]:
        """Fetch RAG context and select system prompt. Returns (context, system_prompt)."""
        context = ""
        try:
            context = self.retriever.get_context("code review patterns and conventions", k=3)
            self._log("Fetched codebase context via RAG")
        except Exception as e:
            self._log(f"RAG context unavailable: {e}")

        if self.settings.LLM_PROVIDER == "local":
            system_prompt = load_prompt("review_prompt_local")
        else:
            system_prompt = load_prompt("review_prompt")

        return context, system_prompt

    def _execute_file_reviews(self, reviewable_files: list, system_prompt: str,
                              context: str, request_id: str, pr_number: int,
                              review_type: str) -> tuple[list, object]:
        """Run per-file reviews via ThreadPoolExecutor. Returns (all_comments, last_response)."""
        max_workers = self._get_max_workers()
        self._log(f"Reviewing {len(reviewable_files)} files with {max_workers} worker(s)...")

        all_parsed_comments = []
        last_response = None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    self._review_single_file, file_data, system_prompt, context,
                    request_id, pr_number, review_type
                )
                for file_data in reviewable_files
            ]

            for future in futures:
                try:
                    result = future.result()
                    for log_line in result["logs"]:
                        self._log(log_line)
                    all_parsed_comments.extend(result["comments"])
                    if result["response"] and result["response"].success:
                        last_response = result["response"]
                except Exception as e:
                    self._log(f"  Unhandled thread exception during file review: {e}")

        return all_parsed_comments, last_response

    def _post_comments(self, pr_number: int, all_parsed_comments: list,
                       reviewable_files: list, last_response, is_incremental: bool,
                       dedup: bool = False) -> list:
        """Post inline comments to GitHub + summary comment. Returns posted comments list."""
        commit_sha = self.github_client.get_latest_commit_sha(pr_number)
        posted = []
        skipped_dedup = 0

        for comment in all_parsed_comments:
            file_path = comment.get("file")
            line = comment.get("line")
            severity = comment.get("severity", "suggestion").upper()
            body = f"**[{severity}]** {comment.get('comment')}"

            if dedup and self.github_client.comment_already_exists(
                pr_number, file_path, line, comment.get("comment", "")[:50]
            ):
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

        self._log(f"Review complete. {len(posted)}/{len(all_parsed_comments)} comments posted across {len(reviewable_files)} files.")

        # Post summary comment
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

        return posted

    # ─── Full PR Review ───────────────────────────────────────────────────

    def review_pr(self, pr_number: int) -> dict:
        """Full PR review pipeline: fetch files → review each file (parallel) → post comments."""
        self.audit_log = []
        request_id = generate_request_id()
        self._log(f"[{request_id}] Starting review for PR #{pr_number}")

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

        context, system_prompt = self._prepare_review()
        all_parsed_comments, last_response = self._execute_file_reviews(
            reviewable_files, system_prompt, context, request_id, pr_number, "full PR"
        )
        posted = self._post_comments(
            pr_number, all_parsed_comments, reviewable_files, last_response,
            is_incremental=False, dedup=False,
        )

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
                    ext = os.path.splitext(file.filename)[1].lower()
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

        # 2. Prepare review (RAG + prompt via shared helper)
        context, system_prompt = self._prepare_review()

        # 3. Execute file reviews (ThreadPoolExecutor via shared helper)
        review_type = "incremental changes" if is_incremental else "full PR"
        all_parsed_comments, last_response = self._execute_file_reviews(
            reviewable_files, system_prompt, context, request_id, pr_number, review_type
        )

        # 4. Post comments with dedup (via shared helper)
        posted = self._post_comments(
            pr_number, all_parsed_comments, reviewable_files, last_response,
            is_incremental=is_incremental, dedup=True,
        )

        # 5. Save reviewed SHA
        new_sha = self.github_client.get_latest_commit_sha(pr_number)
        if new_sha:
            save_reviewed_sha(pr_number, new_sha)

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
        # Strip markdown code fences that local models add
        cleaned = re.sub(r'```(?:json)?\s*', '', output)
        cleaned = re.sub(r'```\s*$', '', cleaned.strip()).strip()
        
        # Determine if it's the new {"comments": []} format or the old [...] format
        comments = []
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and "comments" in parsed:
                comments = parsed["comments"]
            elif isinstance(parsed, list):
                comments = parsed
            else:
                return [], True
        except json.JSONDecodeError:
            # Fallback regex extraction for dict format
            match = re.search(r'\{[^{]*"comments"\s*:\s*\[.*?\]\s*\}', cleaned, re.DOTALL)
            if not match:
                # Fallback to list format
                match = re.search(r'\[\s*\{.*?\}\s*\]', cleaned, re.DOTALL)
            
            if not match:
                return [], True
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict) and "comments" in parsed:
                    comments = parsed["comments"]
                else:
                    comments = parsed
            except json.JSONDecodeError:
                return [], True

        # Normalize the keys: map "message" + "suggestion" -> "comment"
        valid_comments = []
        if isinstance(comments, list):
            for c in comments:
                if not isinstance(c, dict) or "line" not in c:
                    continue
                    
                # If they used the new prompt schema (message + suggestion)
                if "message" in c and "comment" not in c:
                    cat = c.get("category", "")
                    msg = c.get("message", "")
                    sug = c.get("suggestion", "")
                    
                    full_comment = msg
                    if sug:
                        full_comment += f"\n\n**Suggestion:** {sug}"
                    if cat:
                        full_comment = f"**[{cat.upper()}]** {full_comment}"
                        
                    c["comment"] = full_comment

                if "comment" in c:
                    valid_comments.append(c)

        return valid_comments, False

    def _log(self, message: str):
        entry = f"[{datetime.now().isoformat()}] {message}"
        self.audit_log.append(entry)
        logger.info(message)
