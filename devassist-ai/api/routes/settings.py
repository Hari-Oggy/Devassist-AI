from fastapi import APIRouter
from pydantic import BaseModel

from core.pipeline_config import get_pipeline_settings, set_review_mode_override
from core.config import get_settings

router = APIRouter(prefix="/settings", tags=["settings"])



class SettingsUpdate(BaseModel):
    review_mode: str


@router.get("")
async def get_current_settings():
    """Return the current runtime settings."""
    pipe_cfg = get_pipeline_settings()
    cfg = get_settings()
    return {
        "review_mode": pipe_cfg.REVIEW_MODE,
        "llm_model": pipe_cfg.REASON_MODEL if pipe_cfg.REVIEW_MODE == "ensemble" else pipe_cfg.DISTILL_MODEL,
        "llm_provider": cfg.LLM_PROVIDER,
        "rag_enabled": True
    }


@router.put("")
async def update_settings(update: SettingsUpdate):
    """Update runtime settings."""
    if update.review_mode in ["fast", "ensemble"]:
        set_review_mode_override(update.review_mode)
    
    pipe_cfg = get_pipeline_settings()
    return {
        "status": "success", 
        "review_mode": pipe_cfg.REVIEW_MODE,
        "llm_model": pipe_cfg.REASON_MODEL if pipe_cfg.REVIEW_MODE == "ensemble" else pipe_cfg.DISTILL_MODEL,
        "llm_provider": get_settings().LLM_PROVIDER,
        "rag_enabled": True
    }
