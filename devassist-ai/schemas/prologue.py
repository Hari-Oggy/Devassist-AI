from pydantic import BaseModel
from typing import Literal

class FocusArea(BaseModel):
    type: Literal["security", "breaking-change", "high-complexity", "data-integrity", "new-pattern", "architecture", "performance", "testing-gap"]
    severity: Literal["critical", "high", "medium", "info"]
    title: str
    description: str

class KeyChangeSummary(BaseModel):
    summary: str
    description: str

class Complexity(BaseModel):
    level: Literal["low", "medium", "high", "very-high"]
    reasoning: str

class PrologueOut(BaseModel):
    motivation: str | None = None
    outcome: str | None = None
    diagram: str | None = None
    key_changes: list[KeyChangeSummary] = []
    focus_areas: list[FocusArea] = []
    complexity: Complexity
