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
    """Yield an async DSN for a throwaway Postgres (env override or testcontainers).

    Safety guard: tests drop/recreate all tables, so refuse to run against a
    database literally named 'cryptopilot' (the application database) to avoid
    wiping live/dev data. Use 'cryptopilot_test' or leave the env var unset
    (testcontainers).
    """
    env_url = os.environ.get("CP_TEST_DATABASE_URL")
    if env_url:
        if env_url.rstrip("/").endswith("/cryptopilot"):
            raise RuntimeError(
                "Refusing to run tests against the app database 'cryptopilot' — "
                "point CP_TEST_DATABASE_URL at 'cryptopilot_test' instead."
            )
        yield env_url
        return
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture()
async def app_client(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[object]:
    """Return an httpx AsyncClient wired to the app with migrations applied."""
    import base64

    monkeypatch.setenv("CP_DATABASE_URL", postgres_url)
    monkeypatch.setenv("CP_MASTER_KEY", base64.b64encode(b"0" * 32).decode())
    monkeypatch.setenv("CP_JWT_SECRET", "j" * 44)
    monkeypatch.setenv("CP_ENVIRONMENT", "test")
    # Capture SMS OTP codes in-process so tests can complete the 2FA flow.
    monkeypatch.setenv("CP_OTP_TEST_MODE", "1")

    # Fresh settings + schema
    from app.core.config import get_settings

    get_settings.cache_clear()

    from app.db import models  # noqa: F401
    from app.db.base import Base
    from sqlalchemy.ext.asyncio import create_async_engine

    # Fresh schema per test for isolation (rows must not bleed between tests).
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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


# Deterministic owner used across auth tests.
OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "correct horse battery staple"
OWNER_PHONE = "94711234567"  # notify.lk form; 2FA is enabled for the test owner


@pytest.fixture()
async def owner(app_client: object) -> str:
    """Provision the owner account (SMS 2FA enabled) in the test DB.

    Returns the owner's phone number, which the login helpers use to read the
    captured OTP code. Depends on app_client so the schema/settings exist.
    """
    import os

    from app.core.crypto import encrypt
    from app.core.security import hash_password
    from app.db.models import User
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    engine = create_async_engine(os.environ["CP_DATABASE_URL"])
    async with AsyncSession(engine) as s:
        s.add(
            User(
                email=OWNER_EMAIL,
                password_hash=hash_password(OWNER_PASSWORD),
                role="owner",
                phone_encrypted=encrypt(OWNER_PHONE, os.environ["CP_MASTER_KEY"]),
                twofa_enabled=True,
            )
        )
        await s.commit()
    await engine.dispose()
    return OWNER_PHONE


def current_otp(phone: str = OWNER_PHONE) -> str:
    """Return the last captured SMS OTP code for a phone (test-mode helper)."""
    from app.services.otp import _TEST_CODES, normalize_phone

    return _TEST_CODES[normalize_phone(phone)]


async def complete_login(client: object) -> tuple[str, str]:
    """Full SMS-2FA login for the test owner; returns (access, refresh)."""
    resp = await client.post(  # type: ignore[attr-defined]
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "otp", body
    otp_token = body["otp_token"]
    verify = await client.post(  # type: ignore[attr-defined]
        "/api/auth/otp/verify",
        json={"code": current_otp()},
        headers={"Authorization": f"Bearer {otp_token}"},
    )
    assert verify.status_code == 200, verify.text
    tokens = verify.json()
    return tokens["access_token"], tokens["refresh_token"]


async def auth_headers(client: object) -> dict[str, str]:
    """Return Authorization headers for an authenticated owner session."""
    access, _ = await complete_login(client)
    return {"Authorization": f"Bearer {access}"}


@pytest.fixture()
async def db_session(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[object]:
    """Yield an AsyncSession against a freshly-created schema (for service tests)."""
    import base64

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    monkeypatch.setenv("CP_DATABASE_URL", postgres_url)
    monkeypatch.setenv("CP_MASTER_KEY", base64.b64encode(b"0" * 32).decode())
    monkeypatch.setenv("CP_JWT_SECRET", "j" * 44)
    monkeypatch.setenv("CP_ENVIRONMENT", "test")
    monkeypatch.setenv("CP_OTP_TEST_MODE", "1")

    from app.core.config import get_settings

    get_settings.cache_clear()

    from app.db import models  # noqa: F401
    from app.db.base import Base

    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()
