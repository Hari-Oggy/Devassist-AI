"""
Database Layer — DevAssist-AI Phase 5.

Provides an async SQLAlchemy engine, session factory, and Base declarative
class for all ORM models.

Supports two backends:
  1. PostgreSQL (production) — via asyncpg driver
  2. SQLite (local dev fallback) — via aiosqlite driver

If PostgreSQL is unreachable at startup, the system automatically falls back
to a local SQLite file at ./data/devassist.db so the app works without Docker.

Environment variables (from .env):
    DATABASE_URL — PostgreSQL connection string
        e.g. postgresql+asyncpg://user:pass@localhost:5432/devassist
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import os
import socket
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from core.logger import get_logger

logger = get_logger("models.database")

# ── Resolve database URL ──────────────────────────────────────────────
_DEFAULT_URL = "postgresql+asyncpg://devassist:devassist@localhost:5432/devassist"
_CONFIGURED_URL: str = os.environ.get("DATABASE_URL", _DEFAULT_URL)

# Normalise sync postgres:// → asyncpg variant
if _CONFIGURED_URL.startswith("postgresql://"):
    _CONFIGURED_URL = _CONFIGURED_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
if _CONFIGURED_URL.startswith("postgres://"):
    _CONFIGURED_URL = _CONFIGURED_URL.replace("postgres://", "postgresql+asyncpg://", 1)

# ── SQLite fallback path ──────────────────────────────────────────────
_SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "devassist.db")
_SQLITE_URL = f"sqlite+aiosqlite:///{_SQLITE_PATH}"

_using_sqlite = False


def _is_pg_reachable(url: str, timeout: float = 2.0) -> bool:
    """Quick TCP check to see if the PostgreSQL host/port is reachable."""
    try:
        parsed = urlparse(url.replace("postgresql+asyncpg://", "http://"))
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (OSError, socket.timeout, ConnectionRefusedError):
        return False


def _resolve_database_url() -> str:
    """Return the database URL to use — PostgreSQL if reachable, else SQLite."""
    global _using_sqlite

    # If already explicitly sqlite, use it
    if _CONFIGURED_URL.startswith("sqlite"):
        _using_sqlite = True
        return _CONFIGURED_URL

    # Check if PostgreSQL is reachable
    if _is_pg_reachable(_CONFIGURED_URL):
        logger.info("PostgreSQL is reachable — using PostgreSQL backend.")
        _using_sqlite = False
        return _CONFIGURED_URL
    else:
        logger.warning(
            "PostgreSQL is NOT reachable at %s. "
            "Falling back to SQLite at %s. "
            "Start Docker (docker-compose up) to use PostgreSQL.",
            _CONFIGURED_URL, _SQLITE_PATH
        )
        # Ensure data directory exists
        os.makedirs(os.path.dirname(_SQLITE_PATH), exist_ok=True)
        _using_sqlite = True
        return _SQLITE_URL


_DATABASE_URL: str = _resolve_database_url()


# ── Engine (lazy) ─────────────────────────────────────────────────────
_engine = None
_session_factory = None


def _get_engine():
    """Return the singleton async engine, creating it on first call."""
    global _engine
    if _engine is None:
        kwargs = {
            "echo": False,
            "pool_pre_ping": True,
        }
        if not _using_sqlite:
            # PostgreSQL-specific pool settings
            kwargs.update({
                "pool_size": 10,
                "max_overflow": 20,
                "pool_recycle": 300,
            })
        _engine = create_async_engine(_DATABASE_URL, **kwargs)
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


def is_using_sqlite() -> bool:
    """Return True if the system is running on the SQLite fallback."""
    return _using_sqlite


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
    backend = "SQLite" if _using_sqlite else "PostgreSQL"
    logger.info("All database tables created (%s).", backend)


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
