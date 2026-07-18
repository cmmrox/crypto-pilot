"""Integration tests for reliability surfaces (QA-10)."""

from __future__ import annotations

import datetime as dt

import httpx
import pytest


@pytest.mark.asyncio
async def test_deep_health_shape(app_client: httpx.AsyncClient) -> None:
    resp = await app_client.get("/health/deep")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("status", "database", "ingest_overdue", "scheduler_alive", "version"):
        assert key in body


def test_dead_man_overdue_transition() -> None:
    """The dead-man flips overdue only past interval + grace (drill logic)."""
    from app.bot.scheduler import DeadMan

    dm = DeadMan("4h", grace_seconds=900)
    base = dt.datetime(2026, 7, 18, 16, 0, tzinfo=dt.UTC)
    dm.beat(base)
    assert not dm.is_overdue(base + dt.timedelta(hours=4, minutes=10))  # within grace
    assert dm.is_overdue(base + dt.timedelta(hours=4, minutes=20))  # past grace
