"""Regression tests for the app_settings singleton (settings_store).

A missing ORDER BY plus unpinned row creation previously let concurrent
first-access on a fresh database insert duplicate app_settings rows. After that,
a read and a write could resolve to different rows — e.g. the SMS-delivery
toggle returned 200 but the status endpoint kept reporting the old value.
"""

from __future__ import annotations

import asyncio
import base64

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.fixture()
async def fresh_engine(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("CP_DATABASE_URL", postgres_url)
    monkeypatch.setenv("CP_MASTER_KEY", base64.b64encode(b"0" * 32).decode())
    monkeypatch.setenv("CP_JWT_SECRET", "j" * 44)
    monkeypatch.setenv("CP_ENVIRONMENT", "test")

    from app.core.config import get_settings

    get_settings.cache_clear()

    from app.db import models  # noqa: F401
    from app.db.base import Base

    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


async def test_creates_single_pinned_row(fresh_engine: object) -> None:
    from app.db.models import AppSettings
    from app.services.settings_store import SINGLETON_ID, get_settings_row

    async with AsyncSession(fresh_engine, expire_on_commit=False) as s:
        row = await get_settings_row(s)
        await s.commit()
        assert row.id == SINGLETON_ID

    async with AsyncSession(fresh_engine, expire_on_commit=False) as s:
        count = (await s.execute(select(func.count()).select_from(AppSettings))).scalar_one()
    assert count == 1


async def test_seeded_row_uses_approved_risk_profile(fresh_engine: object) -> None:
    """A freshly seeded settings row must carry the owner-approved risk-defined
    profile (ARCHITECTURE §8): 15% risk per long trade at up to 6x leverage.
    Guards the money-path default against a silent revert to the old 2%/3x set."""
    from decimal import Decimal

    from app.services.settings_store import get_settings_row

    async with AsyncSession(fresh_engine, expire_on_commit=False) as s:
        row = await get_settings_row(s)
        await s.commit()
        assert row.risk_pct == Decimal("15")
        assert row.leverage_cap == Decimal("6")


async def test_write_then_read_resolve_same_row(fresh_engine: object) -> None:
    """The exact read-after-write bug: a committed write must be observed by a
    fresh session/connection reading the singleton."""
    from app.services.settings_store import get_settings_row

    async with AsyncSession(fresh_engine, expire_on_commit=False) as s:
        row = await get_settings_row(s)
        row.sms_enabled = False
        await s.commit()

    async with AsyncSession(fresh_engine, expire_on_commit=False) as s:
        row = await get_settings_row(s)
        assert row.sms_enabled is False


async def test_deterministic_when_duplicates_exist(fresh_engine: object) -> None:
    """Even if a legacy database already holds duplicates, reads and writes must
    resolve to the same (lowest-id) canonical row."""
    from app.db.models import AppSettings
    from app.services.settings_store import get_settings_row

    async with AsyncSession(fresh_engine, expire_on_commit=False) as s:
        s.add_all([AppSettings(id=1, sms_enabled=True), AppSettings(id=2, sms_enabled=True)])
        await s.commit()

    async with AsyncSession(fresh_engine, expire_on_commit=False) as s:
        row = await get_settings_row(s)
        assert row.id == 1
        row.sms_enabled = False
        await s.commit()

    async with AsyncSession(fresh_engine, expire_on_commit=False) as s:
        row = await get_settings_row(s)
        assert row.id == 1 and row.sms_enabled is False


async def test_concurrent_first_access_makes_no_duplicates(fresh_engine: object) -> None:
    from app.db.models import AppSettings
    from app.services.settings_store import get_settings_row

    async def create_once() -> int:
        async with AsyncSession(fresh_engine, expire_on_commit=False) as s:
            row = await get_settings_row(s)
            await s.commit()
            return row.id

    ids = await asyncio.gather(*(create_once() for _ in range(8)))

    async with AsyncSession(fresh_engine, expire_on_commit=False) as s:
        count = (await s.execute(select(func.count()).select_from(AppSettings))).scalar_one()
    assert count == 1
    assert set(ids) == {1}
