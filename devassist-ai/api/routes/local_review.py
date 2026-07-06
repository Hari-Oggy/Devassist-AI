from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_db_session
from core.config import get_settings

router = APIRouter(prefix="/local-review", tags=["local-review"])
settings = get_settings()

@router.post("")
async def start_local_review(payload: dict, db: AsyncSession = Depends(get_db_session)):
    if not settings.LOCAL_REVIEW_ENABLED:
        raise HTTPException(status_code=403, detail="Local review is disabled")
    return {"status": "started", "message": "Local review triggered (stub)"}
