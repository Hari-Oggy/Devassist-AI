"""
PostgreSQL Database Layer — DevAssist-AI Phase 5.

Provides an async SQLAlchemy engine, session factory, and Base declarative
class for all ORM models.  Uses asyncpg driver for maximum performance.

Never modifies existing SQLite-based code — this is a standalone new module.

Environment variables (from .env):
    DATABASE_URL — PostgreSQL connection string
        e.g. postgresql+asyncpg://user:pass@localhost:5432/devassist
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from core.logger import get_logger

logger = get_logger("models.database")

# ── Default to asyncpg driver ─────────────────────────────────────────
_DEFAULT_URL = "postgresql+asyncpg://devassist:devassist@localhost:5432/devassist"
_DATABASE_URL: str = os.environ.get("DATABASE_URL", _DEFAULT_URL)

# Normalise sync postgres:// → asyncpg variant
if _DATABASE_URL.startswith("postgresql://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
if _DATABASE_URL.startswith("postgres://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)


# ── Engine (lazy) ─────────────────────────────────────────────────────
# Engine is created on first use to avoid import-time driver errors
# when asyncpg is not installed (e.g., during unit tests with aiosqlite).
_engine = None
_session_factory = None


def _get_engine():
    """Return the singleton async engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _DATABASE_URL,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=300,
        )
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the singleton session factory, creating it on first call."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


# Convenience alias — used by tests and the session context manager
@property  # type: ignore[misc]
def engine():
    return _get_engine()


def AsyncSessionFactory() -> async_sessionmaker[AsyncSession]:
    return _get_session_factory()


# ── Declarative base ───────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Shared declarative base for all DevAssist-AI ORM models."""


# ── Session context manager ────────────────────────────────────────────

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional async database session (for FastAPI Depends)."""
    async with _get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

@asynccontextmanager
async def get_db_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional async database session (for 'async with' blocks)."""
    async for session in get_db_session():
        yield session


async def create_all_tables() -> None:
    """Create all tables defined in the ORM models."""
    from models import entities  # noqa: F401
    async with _get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("All database tables created.")


async def drop_all_tables() -> None:
    """Drop all tables — for testing only."""
    async with _get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.info("All database tables dropped.")


async def check_connection() -> bool:
    """Return True if the database is reachable."""
    try:
        async with _get_engine().connect() as conn:
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Database connection check failed: %s", exc)
        return False
