from pydantic import BaseModel, ConfigDict
from datetime import datetime

class CommentOut(BaseModel):
    id: int
    author: str
    body: str
    is_bot: bool
    created_at: datetime
    edited_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)

class CommentThreadOut(BaseModel):
    id: int
    file_path: str
    line_start: int
    line_end: int
    side: str
    status: str
    github_comment_id: int | None = None
    resolved: bool
    comments: list[CommentOut] = []
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
