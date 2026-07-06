"""
Review worker — Celery task that runs the Ensemble Pipeline asynchronously.
"""

import asyncio
import os
from typing import Any

from taskqueue.celery_app import celery_app
from core.config import get_settings
from core.pipeline_config import get_pipeline_settings
from core.logger import get_logger
from core.repo_config import load_repo_config
from models.database import get_db_session_context
from models.repositories import RepositoryRepo, PullRequestRepo, ReviewRepo, FindingRepo, ReviewEventRepo
from models.entities import ProviderType, EventType, ReviewStatus
from api.sse import sse_manager
from llm.pipeline import ReviewPipeline
from llm.router import LLMRouter
from codegraph.impact_analyzer import ImpactAnalyzer
from codegraph.graph_builder import CodeGraphBuilder
from codegraph.repo_cloner import RepoCloner
from agents.tools.github_tool import get_github_client
from prompts import load_prompt

# RAG Imports (Phase 4)
from rag.ast_chunker import ASTChunker
from rag.hybrid_retriever import HybridRetriever
from rag.embeddings import get_embedding_model
from rag.history_indexer import HistoryIndexer

logger = get_logger("workers.review")
settings = get_settings()


@celery_app.task(
    name="workers.review_worker.run_review",
    bind=True,
    time_limit=settings.REVIEW_TIMEOUT + 30,
    soft_time_limit=settings.REVIEW_TIMEOUT,
    max_retries=1,
)
def run_review(self, context: dict[str, Any]) -> dict:
    """
    Execute a full PR review as a background task.
    Since Celery tasks are synchronous, we run the async code using asyncio.run().

    Args:
        context: Review context dict (from webhook).
    """
    # Reset the SQLAlchemy engine singleton so it binds to the fresh
    # event loop that asyncio.run() creates in this thread.
    from models import database as _db
    if hasattr(_db._thread_local, "engine"):
        _db._thread_local.engine = None
    if hasattr(_db._thread_local, "session_factory"):
        _db._thread_local.session_factory = None

    return asyncio.run(_run_review_async(context))



async def _run_review_async(context: dict[str, Any]) -> dict:
    provider_str = context.get("provider", "github")
    provider = ProviderType.GITHUB if provider_str == "github" else ProviderType.GITLAB
    project_path = context.get("project_path", "")
    project_id = context.get("project_id")
    mr_iid = context.get("mr_iid") or context.get("pr_number")
    
    logger.info(f"Starting async review task for {provider_str} {project_path}#{mr_iid}")

    from core.review_state import acquire_review_lock, release_review_lock
    if not acquire_review_lock(int(mr_iid)):
        logger.warning(f"PR #{mr_iid} already locked — review in progress")
        return {"status": "locked", "pr_number": mr_iid}

    review_id = None
    try:
        async with get_db_session_context() as session:
            # 1. Upsert Repository
            repo = await RepositoryRepo.upsert(
                session=session,
                provider=provider,
                full_name=project_path,
                provider_id=project_id,
            )
            
            active_repo_id = repo.id
            active_repo_settings = repo.settings or {}
            
            # 2. Upsert Pull Request
            pr = await PullRequestRepo.upsert(
                session=session,
                repository_id=repo.id,
                provider_pr_id=int(mr_iid),
                title=context.get("mr_title", ""),
                author=context.get("mr_author", ""),
                source_branch=context.get("source_branch", ""),
                target_branch=context.get("target_branch", ""),
                is_draft=context.get("is_draft", False),
                provider_url=context.get("mr_url", ""),
            )

            # 3. Create Review
            review = await ReviewRepo.create(
                session=session,
                pull_request_id=pr.id,
                mode=get_pipeline_settings().REVIEW_MODE,
                commit_sha=context.get("last_commit_sha", "")
            )
            review_id = review.id

            await ReviewEventRepo.create(
                session=session,
                review_id=review_id,
                event_type=EventType.REVIEW_STARTED,
                message="Review started."
            )
            await sse_manager.publish_review_started(review_id, mode=get_pipeline_settings().REVIEW_MODE)
            
            # 4. Mark Running
            await ReviewRepo.mark_running(session, review_id)

        # 5. Run the Ensemble Pipeline
        # Construct Git clone URL
        if provider == ProviderType.GITLAB:
            gitlab_token = getattr(settings, "GITLAB_TOKEN", None) or ""
            gitlab_api_url = getattr(settings, "GITLAB_API_URL", None) or "https://gitlab.com"
            from urllib.parse import urlparse
            parsed = urlparse(gitlab_api_url)
            host = parsed.netloc or "gitlab.com"
            scheme = parsed.scheme or "https"
            if gitlab_token:
                repo_url = f"{scheme}://oauth2:{gitlab_token}@{host}/{project_path}.git"
            else:
                repo_url = f"{scheme}://{host}/{project_path}.git"
        else:
            installation_id = context.get("installation_id")
            from agents.tools.github_tool import get_github_client
            try:
                github_client = get_github_client(repo_name=project_path, installation_id=installation_id)
            except Exception as e:
                logger.error(f"Failed to init GitHub client for repo {project_path}: {e}")
                raise
                
            clone_token = github_client.get_clone_token()
            if clone_token and clone_token != "your_github_personal_access_token_here":
                repo_url = f"https://x-access-token:{clone_token}@github.com/{project_path}.git"
            else:
                repo_url = f"https://github.com/{project_path}.git"

        # Retrieve reviewable files
        if provider == ProviderType.GITLAB:
            from providers.gitlab_client import GitLabClient
            async with GitLabClient() as client:
                diffs = await client.get_mr_diff(project_path, int(mr_iid))
                reviewable_files = []
                SKIP_EXTENSIONS = {
                    '.class', '.pyc', '.pyo', '.o', '.so', '.dll', '.exe',
                    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.webp',
                    '.woff', '.woff2', '.ttf', '.eot',
                    '.zip', '.tar', '.gz', '.jar', '.war',
                    '.lock', '.map', '.min.js', '.min.css',
                    '.pdf', '.doc', '.docx',
                }
                for d in diffs:
                    if d.get("deleted_file"):
                        continue
                    filename = d.get("new_path") or d.get("old_path")
                    patch = d.get("diff")
                    if not patch or not filename:
                        continue
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in SKIP_EXTENSIONS:
                        continue
                    add_lines = len([line for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++')])
                    del_lines = len([line for line in patch.splitlines() if line.startswith('-') and not line.startswith('---')])
                    status = "modified"
                    if d.get("new_file"):
                        status = "added"
                    elif d.get("renamed_file"):
                        status = "renamed"
                    reviewable_files.append({
                        "filename": filename,
                        "patch": patch,
                        "status": status,
                        "additions": add_lines,
                        "deletions": del_lines,
                    })
        else:
            try:
                gh_repo = github_client.repo
                pr_obj = gh_repo.get_pull(int(mr_iid))
            except Exception as e:
                logger.error(f"Failed to fetch PR #{mr_iid} on repo {project_path}: {e}")
                raise

            SKIP_EXTENSIONS = {
                '.class', '.pyc', '.pyo', '.o', '.so', '.dll', '.exe',
                '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.webp',
                '.woff', '.woff2', '.ttf', '.eot',
                '.zip', '.tar', '.gz', '.jar', '.war',
                '.lock', '.map', '.min.js', '.min.css',
                '.pdf', '.doc', '.docx',
            }
            reviewable_files = []
            for file in pr_obj.get_files():
                if not file.patch:
                    continue
                ext = os.path.splitext(file.filename)[1].lower()
                if ext in SKIP_EXTENSIONS:
                    continue
                reviewable_files.append({
                    "filename": file.filename,
                    "patch": file.patch,
                    "status": file.status,
                    "additions": file.additions,
                    "deletions": file.deletions,
                })
            logger.info(f"Fetched {len(reviewable_files)} reviewable files from GitHub PR #{mr_iid}")

        system_prompt = load_prompt("review_prompt")
        
        # Initialize MCP Client Manager and load active servers from database
        from services.mcp_client import SyncMCPClientManager
        from models.entities import MCPServer
        from sqlalchemy import select
        
        mcp_manager = SyncMCPClientManager()
        try:
            async with get_db_session_context() as session:
                stmt = select(MCPServer).where(MCPServer.is_active == True)
                res = await session.execute(stmt)
                active_servers = res.scalars().all()
                config_list = [
                    {
                        "name": s.name,
                        "command": s.command,
                        "args": s.args
                    } for s in active_servers
                ]
                mcp_manager.load_from_config(config_list)
            mcp_tools = mcp_manager.get_combined_tools()
        except Exception as mcp_err:
            logger.error(f"Failed to load MCP servers: {mcp_err}")
            mcp_tools = []

        def tool_executor(name: str, arguments: dict) -> dict:
            return mcp_manager.call_tool(name, arguments)

        pipeline = ReviewPipeline(
            router=LLMRouter(),
            mcp_tools=mcp_tools if mcp_tools else None,
            tool_executor=tool_executor if mcp_tools else None
            
        )

        all_findings = []
        total_tokens_input = 0
        total_tokens_output = 0
        total_cost_estimate = 0.0
        total_duration = 0.0
        model_used = ""
        provider_used = ""
        results = []

        class DummyResult:
            duration_seconds = 0.0
        result = DummyResult()

        with RepoCloner(repo_url=repo_url) as cloner:
            repo_path = cloner.get_repo_path()
            
            # Load and apply per-repo .devassist.yml config
            repo_config = load_repo_config(repo_path)
            pipeline.mode = repo_config.review.mode
            
            if repo_config.has_custom_rules:
                system_prompt += f"\n\n{repo_config.format_custom_rules_prompt()}"
                
            if repo_config.review.focus_areas:
                system_prompt += "\n\nFocus Areas:\n" + "\n".join(f"- {fa}" for fa in repo_config.review.focus_areas)
                
            if repo_config.review.language_hints:
                system_prompt += "\n\nLanguage Hints:\n" + "\n".join(f"- {lh}" for lh in repo_config.review.language_hints)
                
            reviewable_files = [f for f in reviewable_files if not repo_config.should_skip_file(f["filename"])]
            
            graph = CodeGraphBuilder(
                repo_path,
                skip_patterns=repo_config.review.skip_files
            ).build()
            analyzer = ImpactAnalyzer(graph)
            changed_filenames = [f["filename"] for f in reviewable_files]
            report = analyzer.analyze(changed_files=changed_filenames, pr_number=int(mr_iid))
            impact_report = report.to_dict()

            # --- Static Analysis ---
            from analyzers.static_analyzer import StaticAnalyzer
            logger.info("Running StaticAnalyzer on changed files...")
            try:
                static_analyzer = StaticAnalyzer(max_workers=4)
                
                # Use the first language hint if available, else default to "multi"
                lang = repo_config.review.language_hints[0] if repo_config.review.language_hints else "multi"
                sandbox_result = static_analyzer.analyze(
                    target_path=repo_path,
                    file_paths=changed_filenames,
                    language=lang
                )
                findings_map = sandbox_result.findings_by_file()
                logger.info(f"StaticAnalyzer completed with {len(sandbox_result.all_findings)} findings.")
            except Exception as e:
                logger.warning(f"StaticAnalyzer failed: {e}")
                findings_map = {}
            # -----------------------
            
            # --- Agentic Executor Analysis ---
            from analyzers.agentic_executor import AgenticExecutor
            logger.info("Running AgenticExecutor dynamic analysis...")
            try:
                pr_diff = "\n".join(f["patch"] for f in reviewable_files if f.get("patch"))
                if pr_diff:
                    executor = AgenticExecutor(script_timeout=30)
                    agentic_result = executor.execute_analysis(
                        pr_diff=pr_diff,
                        repo_path=repo_path,
                        pr_number=int(mr_iid),
                        changed_files=changed_filenames,
                    )
                    if agentic_result.success and agentic_result.findings:
                        from analyzers.models import LintFinding, Severity
                        for f in agentic_result.findings:
                            fname = f.get("file")
                            if fname:
                                sev_str = f.get("severity", "warning").upper()
                                sev = Severity.WARNING
                                if sev_str == "ERROR": sev = Severity.ERROR
                                elif sev_str == "NOTE" or sev_str == "INFO": sev = Severity.NOTE
                                
                                lf = LintFinding(
                                    file_path=fname,
                                    line=f.get("line", 0),
                                    message=f"[Agentic] {f.get('message')}",
                                    severity=sev,
                                    rule_id="agentic-dynamic",
                                )
                                if fname not in findings_map:
                                    findings_map[fname] = []
                                findings_map[fname].append(lf)
                        logger.info(f"AgenticExecutor completed with {len(agentic_result.findings)} dynamic findings.")
            except Exception as e:
                logger.warning(f"AgenticExecutor failed: {e}")
            # ---------------------------------

            # --- Persistent RAG Integration ---
            rag_status = active_repo_settings.get("rag_status", "pending")
            retriever = HybridRetriever(get_embedding_model())
            index_loaded = False
            
            if rag_status == "ready":
                index_path = os.path.join("data", "rag_v2", f"repo_{active_repo_id}")
                try:
                    if retriever.load(index_path):
                        index_loaded = True
                        logger.info(f"Loaded persistent RAG index for repo_id={active_repo_id}")
                    else:
                        logger.warning(f"RAG index not found at {index_path} despite 'ready' status.")
                except Exception as e:
                    logger.warning(f"Failed to load RAG index: {e}")

            if not index_loaded:
                logger.info(f"RAG status is '{rag_status}'. Falling back to temporary in-memory index.")
                try:
                    from rag.rag_config import get_rag_settings
                    rag_cfg = get_rag_settings()
                    repo_files = []
                    for root, dirs, files in os.walk(repo_path):
                        dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__', '.venv', 'dist', 'build', '.next')]
                        for file in files:
                            ext = os.path.splitext(file)[1].lower()
                            if ext in rag_cfg.code_extensions:
                                file_path = os.path.join(root, file)
                                if os.path.getsize(file_path) <= rag_cfg.RAG_MAX_FILE_BYTES:
                                    try:
                                        with open(file_path, 'r', encoding='utf-8') as f:
                                            repo_files.append({"file_path": file_path, "content": f.read()})
                                    except Exception:
                                        pass
                    
                    logger.info(f"Chunking {len(repo_files)} files for temporary RAG...")
                    chunker = ASTChunker()
                    chunks = chunker.chunk_files(repo_files)
                    retriever.build(chunks)
                    logger.info("Temporary RAG indexing complete")
                except Exception as e:
                    logger.warning(f"Temporary RAG indexing failed: {e}")

            def process_file(file_data):
                # Retrieve context from RAG
                filename = file_data.get("filename", "")
                patch = file_data.get("patch", "")
                rag_context = ""
                if 'retriever' in locals():
                    try:
                        # Use simple format for context injection
                        rag_context = retriever.retrieve_as_context(f"Review changes in {filename}:\n{patch[:500]}", k=5)
                    except Exception as e:
                        logger.warning(f"Failed to retrieve context for {filename}: {e}")

                # Format lint results for this file
                file_lint_result = ""
                file_findings = []
                for f_path, f_list in findings_map.items():
                    if filename.replace("\\", "/") in f_path.replace("\\", "/"):
                        file_findings.extend(f_list)
                
                if file_findings:
                    lines = []
                    for lf in file_findings:
                        sev = lf.severity.value if hasattr(lf.severity, "value") else str(lf.severity)
                        lines.append(f"[{lf.tool}] line {lf.line}: {sev} ({lf.rule_id}) {lf.message}")
                    file_lint_result = "\n".join(lines)

                return pipeline.run(
                    file_data=file_data,
                    system_prompt=system_prompt,
                    impact_report=impact_report,
                    pr_number=int(mr_iid),
                    context=rag_context,
                    lint_result=file_lint_result,
                )

            import concurrent.futures
            max_concurrency = 5  # Limit concurrent API calls to avoid immediate rate limits
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrency) as pool:
                # pool.map guarantees the results array is in the same order as reviewable_files
                results = list(pool.map(process_file, reviewable_files))
            
            for result in results:
                all_findings.extend(result.findings)
                total_tokens_input += result.total_tokens_input
                total_tokens_output += result.total_tokens_output
                total_cost_estimate += result.total_cost_estimate
                total_duration += result.duration_seconds
                if result.model_used:
                    model_used = result.model_used
                if result.provider_used:
                    provider_used = result.provider_used

        # 6. Save findings
        async with get_db_session_context() as session:
            findings_dicts = []
            for f in all_findings:
                fd = f.dict()
                
                # Defensive mapping of severity
                sev = str(fd.get("severity") or "").lower().strip()
                if sev == "suggestion" or sev not in ["error", "warning", "note"]:
                    fd["severity"] = "note"
                else:
                    fd["severity"] = sev
                
                # Defensive mapping of category
                cat = str(fd.get("category") or "").lower().strip()
                if cat == "unknown" or cat not in ["security", "correctness", "reliability", "performance", "maintainability", "style", "vulnerability"]:
                    fd["category"] = "maintainability"
                else:
                    fd["category"] = cat
                
                findings_dicts.append(fd)

            await FindingRepo.bulk_create(session, review_id, findings_dicts)
            
            error_count = sum(1 for fd in findings_dicts if fd.get("severity") == "error")
            warning_count = sum(1 for fd in findings_dicts if fd.get("severity") == "warning")
            summaries = [f"File {f.get('filename')}: {res.distillation.summary}" for f, res in zip(reviewable_files, results) if res.distillation and res.distillation.summary]
            raw_summary = "\n".join(summaries) if summaries else f"Review completed. Found {len(all_findings)} issues across {len(reviewable_files)} files."

            # Post GitHub Comments
            if provider == ProviderType.GITHUB and 'gh_repo' in locals():
                try:
                    pr_obj = gh_repo.get_pull(int(mr_iid))
                    commit_sha = context.get("last_commit_sha", "")
                    if commit_sha:
                        gh_commit = gh_repo.get_commit(commit_sha)
                        for fd in findings_dicts:
                            # Only post errors and warnings that have file/line data
                            if fd.get("severity") in ["error", "warning"] and fd.get("file") and fd.get("line"):
                                # Dedup check
                                already_exists = False
                                for comment in pr_obj.get_review_comments():
                                    if ("<!-- devassist-ai -->" in (comment.body or "") 
                                        and comment.path == fd["file"] 
                                        and getattr(comment, 'line', comment.position) == fd["line"] 
                                        and fd["comment"][:50] in (comment.body or "")):
                                        already_exists = True
                                        break
                                
                                if not already_exists:
                                    body_text = f"**{fd['severity'].upper()}** ({fd['category']}): {fd['comment']}"
                                    if fd.get("code_fix"):
                                        body_text += f"\n\n```suggestion\n{fd['code_fix']}\n```"
                                    marked_body = f"{body_text}\n\n<!-- devassist-ai -->"
                                    
                                    try:
                                        pr_obj.create_review_comment(
                                            body=marked_body,
                                            commit=gh_commit,
                                            path=fd["file"],
                                            line=int(fd["line"]),
                                            side="RIGHT"
                                        )
                                        logger.info(f"Posted inline comment to {fd['file']}:{fd['line']}")
                                    except Exception as e:
                                        logger.warning(f"Failed to post inline comment to {fd['file']}:{fd['line']} (often due to line not in diff hunk): {e}")

                    # Post summary comment — CodeRabbit-style
                    try:
                        # ── Walkthrough ────────────────────────────────────────
                        walkthrough_lines = []
                        for file_data, res in zip(reviewable_files, results):
                            if res.distillation and res.distillation.summary:
                                walkthrough_lines.append(
                                    f"- **`{file_data['filename']}`** — {res.distillation.summary}"
                                )
                        walkthrough_section = (
                            "### 🔍 Walkthrough\n\n"
                            + ("\n".join(walkthrough_lines) if walkthrough_lines
                               else f"Reviewed {len(reviewable_files)} file(s). "
                                    f"Found {len(all_findings)} issue(s) total.")
                        )

                        # ── Changes table ──────────────────────────────────────
                        changes_rows = []
                        for file_data, res in zip(reviewable_files, results):
                            status_icon = {"added": "🆕", "removed": "🗑️", "renamed": "✏️"}.get(
                                file_data.get("status", ""), "📝"
                            )
                            ct = res.distillation.change_type if res.distillation else "modified"
                            changes_rows.append(
                                f"| {status_icon} `{file_data['filename']}` "
                                f"| +{file_data.get('additions', 0)} / -{file_data.get('deletions', 0)} "
                                f"| {ct} |"
                            )
                        changes_section = (
                            "### 📋 Changes\n\n"
                            "| File | Diff | Change Type |\n"
                            "|---|---|---|\n"
                            + "\n".join(changes_rows)
                        )

                        # ── Quality score ──────────────────────────────────────
                        note_count = sum(1 for fd in findings_dicts if fd.get("severity") == "note")
                        penalty = min(error_count * 2 + warning_count * 0.5 + note_count * 0.1, 10)
                        quality_score = max(0, round(10 - penalty, 1))
                        score_emoji = "🟢" if quality_score >= 8 else ("🟡" if quality_score >= 5 else "🔴")
                        quality_section = (
                            f"### {score_emoji} PR Quality Score: **{quality_score}/10**\n\n"
                            f"| Severity | Count |\n|---|---|\n"
                            f"| 🔴 Errors | {error_count} |\n"
                            f"| 🟡 Warnings | {warning_count} |\n"
                            f"| 🔵 Notes | {note_count} |"
                        )

                        # ── Blast radius ────────────────────────────────────────
                        blast_section = ""
                        if impact_report:
                            blast_items = []
                            affected = impact_report.get("affected_files", [])
                            if affected:
                                for aff in affected[:10]:  # cap at 10
                                    fname = aff if isinstance(aff, str) else aff.get("file", str(aff))
                                    blast_items.append(f"- `{fname}`")
                                blast_section = (
                                    "### 🕸️ Blast Radius\n\n"
                                    "These files may be indirectly affected by this PR:\n\n"
                                    + "\n".join(blast_items)
                                    + ("\n\n_...and more._" if len(affected) > 10 else "")
                                )

                        # ── Findings detail ────────────────────────────────────
                        findings_detail_lines = []
                        for fd in findings_dicts:
                            sev = fd.get("severity", "note")
                            if sev not in ["error", "warning", "note"]:
                                continue
                            sev_icon = {"error": "🔴", "warning": "🟡", "note": "🔵"}.get(sev, "ℹ️")
                            file_ref = f"`{fd.get('file', '?')}:{fd.get('line', '?')}`"
                            findings_detail_lines.append(
                                f"| {sev_icon} **{sev.upper()}** | {file_ref} | {fd.get('category', '')} | {fd.get('comment', '')} |"
                            )
                            if fd.get("code_fix"):
                                lang = "python" if fd.get("file", "").endswith(".py") else \
                                       "typescript" if fd.get("file", "").endswith((".ts", ".tsx")) else \
                                       "javascript" if fd.get("file", "").endswith((".js", ".jsx")) else ""
                                findings_detail_lines.append(
                                    f"\n  <details><summary>Suggested fix</summary>\n\n"
                                    f"  ```{lang}\n  {fd['code_fix'].strip()}\n  ```\n\n  </details>"
                                )

                        findings_section = ""
                        if findings_detail_lines:
                            findings_section = (
                                "### 🐛 Findings\n\n"
                                "| Severity | Location | Category | Message |\n"
                                "|---|---|---|---|\n"
                                + "\n".join(findings_detail_lines)
                            )

                        # ── Assemble full comment ──────────────────────────────
                        parts = [walkthrough_section, changes_section, quality_section]
                        if blast_section:
                            parts.append(blast_section)
                        if findings_section:
                            parts.append(findings_section)

                        full_comment = "\n\n".join(parts) + "\n\n<!-- devassist-ai -->"
                        pr_obj.create_issue_comment(full_comment)
                        logger.info("Posted enriched summary comment to GitHub PR")
                    except Exception as e:
                        logger.error(f"Failed to build/post summary comment: {e}")
                except Exception as e:
                    logger.error(f"Failed to post comments to GitHub: {e}")

            # 7. Generate Prologue & Chapters (Ensemble mode only)
            prologue_dict = None
            db_chapters = []   # guaranteed-defined before pipeline_meta build
            docs_out = []      # guaranteed-defined before pipeline_meta build
            if pipeline.mode == "ensemble":
                try:
                    from llm.chapter_clusterer import ChapterClusterer
                    from llm.prologue_synthesizer import PrologueSynthesizer
                    from models.chapter import Chapter

                    logger.info("Starting Chapter Clustering & Prologue Synthesis")
                    
                    clusterer = ChapterClusterer(pipeline.router)
                    chapters_out = await clusterer.cluster(reviewable_files, impact_report)
                    
                    # Convert to DB models and save
                    for c_out in chapters_out:
                        chapter = Chapter(
                            review_id=review_id,
                            external_id=str(c_out.id),
                            order=c_out.order,
                            title=c_out.title,
                            summary=c_out.summary,
                        )
                        session.add(chapter)
                        db_chapters.append(c_out.dict())
                    
                    synthesizer = PrologueSynthesizer(pipeline.router)
                    commits = []
                    if provider == ProviderType.GITHUB and 'gh_repo' in locals():
                        gh_pr = gh_repo.get_pull(int(mr_iid))
                        commits = [c.commit.message for c in gh_pr.get_commits()]
                    
                    prologue_out = await synthesizer.synthesize(
                        chapters=db_chapters,
                        commit_messages=commits,
                        pr_title=context.get("mr_title", ""),
                        pr_body=""
                    )
                    prologue_dict = prologue_out.model_dump()
                    
                    logger.info(
                        "Successfully generated Prologue and Chapters — "
                        "diagram=%s, focus_areas=%d, complexity=%s",
                        "present" if prologue_dict.get("diagram") else "null",
                        len(prologue_dict.get("focus_areas", [])),
                        prologue_dict.get("complexity", {}).get("level", "unknown")
                    )
                    
                    try:
                        from llm.documentation_synthesizer import DocumentationSynthesizer
                        logger.info("Starting Documentation Synthesis")
                        doc_synth = DocumentationSynthesizer(pipeline.router)
                        docs_out = await doc_synth.generate_docs(reviewable_files)
                        logger.info(f"Generated docs for {len(docs_out)} files")
                    except Exception as ed:
                        logger.error(f"Failed to synthesize documentation: {ed}")
                        docs_out = []
                        
                except Exception as e:
                    logger.error(f"Failed to synthesize prologue/chapters: {e}")

            await ReviewRepo.mark_completed(
                session=session, 
                review_id=review_id, 
                total_findings=len(all_findings),
                error_count=error_count,
                warning_count=warning_count,
                duration_seconds=total_duration,
                total_tokens_input=total_tokens_input,
                total_tokens_output=total_tokens_output,
                cost_estimate=total_cost_estimate,
                model_used=model_used,
                provider_used=provider_used,
                raw_summary=raw_summary,
                prologue_json=prologue_dict,
                pipeline_meta={
                    "mode": pipeline.mode,
                    "files_count": len(reviewable_files),
                    "impact_report": impact_report,  # persist blast-radius for frontend
                    "chapters": db_chapters,
                    "documentation": docs_out,
                    # Preserve installation_id so chapter-diff route can re-auth
                    "installation_id": context.get("installation_id"),
                }
            )
            await ReviewEventRepo.create(
                session=session,
                review_id=review_id,
                event_type=EventType.REVIEW_COMPLETED,
                message=f"Review completed. Found {len(all_findings)} issues."
            )
            await sse_manager.publish_review_completed(
                review_id,
                findings_count=len(all_findings),
                duration_seconds=total_duration
            )

        # 7. Persist review to history (project memory)
        try:
            diff_summary = f"{len(all_findings)} findings across {len(reviewable_files)} file(s)"
            history_indexer = HistoryIndexer(get_embedding_model())
            history_indexer.load()
            history_indexer.add_review(
                pr_number=int(mr_iid),
                repo=project_path,
                title=context.get("mr_title", ""),
                diff_summary=diff_summary,
                findings=[f.dict() for f in all_findings],
                resolution="open",
                metadata={"mode": pipeline.mode, "model": model_used},
            )
            logger.info(f"HistoryIndexer: saved PR #{mr_iid} review to project memory")
        except Exception as hist_err:
            logger.warning(f"HistoryIndexer failed (non-fatal): {hist_err}")
        return {
            "success": True,
            "findings_count": len(all_findings),
            "mode": pipeline.mode,
            "duration": total_duration,
        }

    except Exception as e:
        logger.error(f"Review failed: {e}")
        if review_id is not None:
            async with get_db_session_context() as session:
                await ReviewRepo.mark_failed(session, review_id, error_message=str(e))
                await ReviewEventRepo.create(
                    session=session,
                    review_id=review_id,
                    event_type=EventType.REVIEW_FAILED,
                    message=f"Review failed: {str(e)}"
                )
                await sse_manager.publish_review_failed(review_id, str(e))
        return {"success": False, "error": str(e)}
    finally:
        if 'mcp_manager' in locals() and mcp_manager:
            try:
                mcp_manager.shutdown()
                logger.info("Shutdown active MCP server connections.")
            except Exception as shutdown_err:
                logger.warning(f"Error shutting down MCP manager: {shutdown_err}")
        release_review_lock(int(mr_iid))
        
        # Cleanly dispose the database engine before event loop closes
        from models.database import _get_engine
        try:
            await _get_engine().dispose()
        except Exception:
            pass
