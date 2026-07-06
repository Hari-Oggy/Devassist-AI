from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from models.database import get_db_session
from schemas.comment_thread import CommentThreadOut
from services.comment_service import CommentService

router = APIRouter(prefix="/reviews/{review_id}/threads", tags=["comments"])

@router.get("", response_model=List[CommentThreadOut])
async def list_threads(review_id: int, db: AsyncSession = Depends(get_db_session)):
    return await CommentService.get_threads_for_review(db, review_id)
