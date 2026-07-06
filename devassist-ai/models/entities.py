"""
ORM Entities — DevAssist-AI Phase 5.

Defines all PostgreSQL table schemas using SQLAlchemy async-compatible ORM.
Each entity maps 1:1 to a database table.

Tables:
    repositories   — GitHub / GitLab repos being monitored
    pull_requests  — PRs / MRs tracked per repo
    reviews        — Code review runs (one per PR event)
    findings       — Individual lint/LLM findings per review
    review_events  — Audit trail of status changes & SSE events
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON, TypeDecorator
from models.database import Base


# ── Cross-dialect JSON type ───────────────────────────────────────────────

class CompatibleJSON(TypeDecorator):
    """JSONB on PostgreSQL, JSON elsewhere (e.g. SQLite for tests).

    Using JSONB in production gives us indexable, queryable JSON.
    Using JSON in tests avoids the aiosqlite / SQLite dialect error.
    """
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


from sqlalchemy.orm import Mapped, mapped_column, relationship


# ── Enums ──────────────────────────────────────────────────────────────

class ProviderType(str, enum.Enum):
    GITHUB = "github"
    GITLAB = "gitlab"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class FindingSeverity(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"


class FindingCategory(str, enum.Enum):
    SECURITY = "security"
    CORRECTNESS = "correctness"
    RELIABILITY = "reliability"
    PERFORMANCE = "performance"
    MAINTAINABILITY = "maintainability"
    STYLE = "style"
    VULNERABILITY = "vulnerability"


class EventType(str, enum.Enum):
    REVIEW_STARTED = "review_started"
    REVIEW_COMPLETED = "review_completed"
    REVIEW_FAILED = "review_failed"
    FINDING_ADDED = "finding_added"
    COMMENT_POSTED = "comment_posted"
    WEBHOOK_RECEIVED = "webhook_received"
    PROLOGUE_GENERATED = "prologue_generated"
    CHAPTER_STARTED = "chapter_started"
    CHAPTER_COMPLETED = "chapter_completed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Repository ─────────────────────────────────────────────────────────

class Repository(Base):
    """A GitHub or GitLab repository being monitored by DevAssist-AI.

    Attributes:
        id: Primary key.
        provider: Source control provider (github | gitlab).
        full_name: Repository identifier e.g. ``'owner/repo'``.
        provider_id: Platform-specific numeric repository ID.
        default_branch: Default branch name (usually ``'main'``).
        is_active: When False, skip processing events for this repo.
        webhook_secret: HMAC secret used to verify webhook payloads.
        settings: Per-repo JSON config overrides.
        created_at / updated_at: Timestamps.
    """

    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(
        SAEnum(ProviderType, name="provider_type", native_enum=False), nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    webhook_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    settings: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    pull_requests: Mapped[list["PullRequest"]] = relationship(
        "PullRequest", back_populates="repository", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("provider", "full_name", name="uq_repo_provider_fullname"),
        Index("ix_repo_full_name", "full_name"),
        Index("ix_repo_provider", "provider"),
    )

    def __repr__(self) -> str:
        return f"<Repository {self.provider}:{self.full_name}>"


# ── PullRequest ────────────────────────────────────────────────────────

class PullRequest(Base):
    """A pull request (GitHub) or merge request (GitLab).

    Attributes:
        id: Primary key.
        repository_id: FK to the owning repository.
        provider_pr_id: Platform-specific PR/MR number.
        title: PR title.
        author: PR author's username.
        source_branch / target_branch: Branch names.
        is_draft: True for draft/WIP PRs.
        state: Current state (open | closed | merged).
        provider_url: URL to the PR on the platform.
        diff_size: Total diff size in characters.
        created_at / updated_at: Timestamps.
    """

    __tablename__ = "pull_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    provider_pr_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    state: Mapped[str] = mapped_column(String(50), default="open", nullable=False)
    provider_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    repository: Mapped["Repository"] = relationship("Repository", back_populates="pull_requests")
    reviews: Mapped[list["Review"]] = relationship(
        "Review", back_populates="pull_request", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("repository_id", "provider_pr_id", name="uq_pr_repo_provider_id"),
        Index("ix_pr_repository_id", "repository_id"),
        Index("ix_pr_state", "state"),
    )

    def __repr__(self) -> str:
        return f"<PullRequest #{self.provider_pr_id} state={self.state}>"


# ── Review ─────────────────────────────────────────────────────────────

class Review(Base):
    """A single code review run triggered for a pull request.

    One PR may have multiple Review records (e.g., after each push).

    Attributes:
        id: Primary key.
        pull_request_id: FK to the associated PullRequest.
        status: Current review status enum.
        mode: Review mode ('fast' | 'ensemble').
        model_used: Primary LLM model identifier.
        provider_used: LLM provider name.
        total_findings: Count of findings produced.
        error_count / warning_count: Severity breakdowns.
        duration_seconds: Wall-clock time for the review.
        total_tokens_input / total_tokens_output: LLM token usage.
        cost_estimate: Estimated USD cost for LLM calls.
        error_message: Set when status=FAILED.
        commit_sha: Git commit SHA that triggered this review.
        raw_summary: Full LLM summary text.
        pipeline_meta: JSON blob with pipeline stage details.
        created_at / completed_at: Timestamps.
    """

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pull_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        SAEnum(ReviewStatus, name="review_status", native_enum=False),
        default=ReviewStatus.PENDING,
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(String(50), default="fast", nullable=False)
    model_used: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    total_findings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_tokens_input: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens_output: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    pipeline_meta: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)
    prologue_json: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    pull_request: Mapped["PullRequest"] = relationship("PullRequest", back_populates="reviews")
    findings: Mapped[list["Finding"]] = relationship(
        "Finding", back_populates="review", cascade="all, delete-orphan"
    )
    events: Mapped[list["ReviewEvent"]] = relationship(
        "ReviewEvent", back_populates="review", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_review_pull_request_id", "pull_request_id"),
        Index("ix_review_status", "status"),
        Index("ix_review_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Review #{self.id} status={self.status} findings={self.total_findings}>"


# ── Finding ────────────────────────────────────────────────────────────

class Finding(Base):
    """An individual code finding produced during a review.

    Attributes:
        id: Primary key.
        review_id: FK to the parent Review.
        file_path: Source file path where the finding was detected.
        line_start / line_end: Line range of the finding.
        severity: error | warning | note.
        category: Functional category of the finding.
        rule_id: Tool-specific rule identifier (e.g. 'B101', 'E501').
        tool_source: Which tool produced the finding.
        message: Human-readable description.
        code_fix: Optional suggested code fix snippet.
        confidence: LLM/validator confidence score (0.0–1.0).
        is_suppressed: True if the finding was dismissed/suppressed.
        suppression_reason: Why the finding was suppressed.
    """

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True
    )
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    line_start: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    line_end: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    severity: Mapped[str] = mapped_column(
        SAEnum(FindingSeverity, name="finding_severity", native_enum=False),
        default=FindingSeverity.WARNING,
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        SAEnum(FindingCategory, name="finding_category", native_enum=False),
        default=FindingCategory.MAINTAINABILITY,
        nullable=False,
    )
    rule_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    tool_source: Mapped[str] = mapped_column(String(100), default="llm", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    code_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_suppressed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    suppression_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    review: Mapped["Review"] = relationship("Review", back_populates="findings")

    __table_args__ = (
        Index("ix_finding_review_id", "review_id"),
        Index("ix_finding_severity", "severity"),
        Index("ix_finding_file_path", "file_path"),
    )

    def __repr__(self) -> str:
        return f"<Finding {self.severity} {self.file_path}:{self.line_start} [{self.rule_id}]>"


# ── ReviewEvent ────────────────────────────────────────────────────────

class ReviewEvent(Base):
    """Audit trail entry and SSE-publishable event for a review.

    Every significant state change in a review is recorded as an event.
    The SSE manager streams these events to connected frontend clients.

    Attributes:
        id: Primary key.
        review_id: FK to the parent Review.
        event_type: Type of event (see EventType enum).
        message: Human-readable event description.
        data: Optional JSON payload with event-specific data.
        created_at: When this event occurred.
    """

    __tablename__ = "review_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(
        SAEnum(EventType, name="event_type", native_enum=False), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    data: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    review: Mapped["Review"] = relationship("Review", back_populates="events")

    __table_args__ = (
        Index("ix_event_review_id", "review_id"),
        Index("ix_event_type", "event_type"),
        Index("ix_event_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ReviewEvent {self.event_type} review_id={self.review_id}>"


# ── MCPServer ─────────────────────────────────────────────────────────

class MCPServer(Base):
    """Configuration for an Anthropic Model Context Protocol (MCP) server.

    Allows DevAssist to connect to third-party tools (like Notion, Linear)
    by standardizing communication over JSON-RPC.
    """

    __tablename__ = "mcp_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    transport_type: Mapped[str] = mapped_column(String(50), default="stdio", nullable=False)
    command: Mapped[str | None] = mapped_column(String(255), nullable=True)
    args: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of arguments
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # For SSE transport
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<MCPServer {self.name} active={self.is_active}>"

