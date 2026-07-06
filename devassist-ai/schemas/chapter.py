from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

class LineRef(BaseModel):
    file_path: str
    side: Literal["additions", "deletions"]
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

class KeyChangeOut(BaseModel):
    id: int
    content: str
    line_refs: list[LineRef]
    model_config = ConfigDict(from_attributes=True)

class ChapterOut(BaseModel):
    id: int
    order: int
    title: str
    summary: str
    key_changes: list[KeyChangeOut]
    file_paths: list[str]
    finding_count: int
    model_config = ConfigDict(from_attributes=True)
