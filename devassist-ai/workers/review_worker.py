"""
Review worker — Celery task that runs the Ensemble Pipeline asynchronously.
"""

import asyncio
import os
from typing import Any

from taskqueue.celery_app import celery_app
from core.config import get_settings
from core.logger import get_logger
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
    # event loop that asyncio.run() creates. Without this, on Windows the
    # engine holds a reference to a closed loop from a previous run.
    from models import database as _db
    _db._engine = None
    _db._session_factory = None

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
                commit_sha=context.get("last_commit_sha", "")
            )
            review_id = review.id

            await ReviewEventRepo.create(
                session=session,
                review_id=review_id,
                event_type=EventType.REVIEW_STARTED,
                message="Review started."
            )
            await sse_manager.publish_review_started(review_id)
            
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
            github_token = settings.GITHUB_TOKEN or os.getenv("GITHUB_TOKEN")
            if github_token and github_token != "your_github_personal_access_token_here":
                repo_url = f"https://x-access-token:{github_token}@github.com/{project_path}.git"
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
            # Directly use PyGithub with the repo from the webhook payload
            # This avoids the GITHUB_REPO env requirement in GitHubClient.__init__
            github_token = settings.GITHUB_TOKEN or os.getenv("GITHUB_TOKEN")
            from github import Github, Auth as GHAuth
            gh = Github(github_token) if github_token else Github()
            gh_repo = gh.get_repo(project_path)
            pr_obj = gh_repo.get_pull(int(mr_iid))
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
        pipeline = ReviewPipeline(router=LLMRouter())

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
            graph = CodeGraphBuilder(repo_path).build()
            analyzer = ImpactAnalyzer(graph)
            changed_filenames = [f["filename"] for f in reviewable_files]
            report = analyzer.analyze(changed_files=changed_filenames, pr_number=int(mr_iid))
            impact_report = report.to_dict()

            for file_data in reviewable_files:
                result = pipeline.run(
                    file_data=file_data,
                    system_prompt=system_prompt,
                    impact_report=impact_report,
                    pr_number=int(mr_iid),
                )
                results.append(result)
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
                pipeline_meta={"mode": pipeline.mode, "files_count": len(reviewable_files)}
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
                duration_seconds=result.duration_seconds
            )
        
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
        release_review_lock(int(mr_iid))
