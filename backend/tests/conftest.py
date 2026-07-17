"""Shared pytest fixtures.

Integration tests use a real PostgreSQL via testcontainers (falls back to
CP_TEST_DATABASE_URL if provided, e.g. in CI where a service container exists).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Yield an async DSN for a throwaway Postgres (env override or testcontainers)."""
    env_url = os.environ.get("CP_TEST_DATABASE_URL")
    if env_url:
        yield env_url
        return
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture()
async def app_client(postgres_url: str) -> AsyncIterator[object]:
    """Return an httpx AsyncClient wired to the app with migrations applied."""
    import base64

    os.environ["CP_DATABASE_URL"] = postgres_url
    os.environ.setdefault("CP_MASTER_KEY", base64.b64encode(b"0" * 32).decode())
    os.environ.setdefault("CP_JWT_SECRET", "j" * 44)

    # Fresh settings + schema
    from app.core.config import get_settings

    get_settings.cache_clear()

    from app.db import models  # noqa: F401
    from app.db.base import Base
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    import httpx
    from app.db.session import dispose_engine
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await dispose_engine()
