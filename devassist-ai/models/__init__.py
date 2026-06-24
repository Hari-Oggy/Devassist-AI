"""
Models package — PostgreSQL ORM for DevAssist-AI Phase 5.
"""

from models.database import Base, get_db_session
from models.entities import (
    Repository,
    PullRequest,
    Review,
    Finding,
    ReviewEvent,
    ProviderType,
    ReviewStatus,
    FindingSeverity,
    FindingCategory,
    EventType,
)
from models.repositories import (
    RepositoryRepo,
    PullRequestRepo,
    ReviewRepo,
    FindingRepo,
    ReviewEventRepo,
)

__all__ = [
    # Database
    "Base", "get_db_session",
    # Entities
    "Repository", "PullRequest", "Review", "Finding", "ReviewEvent",
    # Enums
    "ProviderType", "ReviewStatus", "FindingSeverity", "FindingCategory", "EventType",
    # Repositories
    "RepositoryRepo", "PullRequestRepo", "ReviewRepo", "FindingRepo", "ReviewEventRepo",
]
