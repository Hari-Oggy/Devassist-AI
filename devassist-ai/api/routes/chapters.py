from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from models.database import get_db_session
from schemas.chapter import ChapterOut
from schemas.prologue import PrologueOut
from services.chapter_service import ChapterService
from llm.prologue_synthesizer import PrologueSynthesizer

router = APIRouter(prefix="/reviews/{review_id}", tags=["chapters"])

@router.get("/chapters", response_model=List[ChapterOut])
async def list_chapters(review_id: int, db: AsyncSession = Depends(get_db_session)):
    return await ChapterService.get_chapters_for_review(db, review_id)

@router.get("/prologue", response_model=PrologueOut)
async def get_prologue(review_id: int, db: AsyncSession = Depends(get_db_session)):
    from models.entities import Review
    from fastapi import HTTPException
    from sqlalchemy.future import select
    
    result = await db.execute(select(Review).filter(Review.id == review_id))
    review = result.scalars().first()
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
        
    if not review.prologue_json:
        raise HTTPException(status_code=404, detail="Prologue not yet generated")
        
    return review.prologue_json


@router.get("/chapters/{chapter_id}/diff")
async def get_chapter_diff(review_id: int, chapter_id: int, db: AsyncSession = Depends(get_db_session)):
    from models.entities import Review, PullRequest
    from fastapi import HTTPException
    from sqlalchemy.future import select
    from sqlalchemy.orm import selectinload
    
    # 1. Fetch Review -> PullRequest -> Repository
    result = await db.execute(
        select(Review)
        .options(selectinload(Review.pull_request).selectinload(PullRequest.repository))
        .filter(Review.id == review_id)
    )
    review = result.scalars().first()
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
        
    if not review.pipeline_meta or "chapters" not in review.pipeline_meta:
        raise HTTPException(status_code=404, detail="Chapters not found in review")
        
    # 2. Find the chapter
    chapter = next((c for c in review.pipeline_meta["chapters"] if c.get("id") == chapter_id), None)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
        
    file_paths = set(chapter.get("file_paths", []))
    
    pr = review.pull_request
    repo = pr.repository
    
    # 3. Fetch patches from the provider
    patch_text = ""
    if repo.provider == "github":
        from agents.tools.github_tool import get_github_client
        # Recover installation_id from pipeline_meta if the repo was added via App auth
        installation_id = None
        if review.pipeline_meta:
            installation_id = review.pipeline_meta.get("installation_id")
        client = get_github_client(repo_name=repo.full_name, installation_id=installation_id)
        reviewable_files = client.get_reviewable_files(pr.provider_pr_id)
        for f in reviewable_files:
            if f["filename"] in file_paths and f.get("patch"):
                patch_text += f"--- a/{f['filename']}\n+++ b/{f['filename']}\n{f['patch']}\n"
    else:
        # GitLab fallback (could use gitlab_client, but skipping for brevity)
        patch_text = "--- a/example\n+++ b/example\n@@ -0,0 +1 @@\n+// GitLab diffs not yet implemented in frontend proxy"
        
    if not patch_text:
        patch_text = "--- a/empty\n+++ b/empty\n@@ -0,0 +0,0 @@\n+// No changes found or unable to fetch diff"
        
    return {"diff": patch_text}
