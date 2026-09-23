"""Async database engine and session management."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging import get_logger

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use."""
    global _engine, _sessionmaker
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            str(settings.database_url),
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the session factory."""
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a session with commit/rollback handling."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the engine (shutdown)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None


async def database_ok(session: AsyncSession) -> bool:
    """Whether the database answers a trivial query. Health probes report, never raise."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        get_logger("db").warning("database_unreachable", error_type=type(exc).__name__)
        return False
    return True
