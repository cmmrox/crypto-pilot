"""A DEMO monthly loss must not halt an independent LIVE account."""

import datetime as dt
from decimal import Decimal

import pytest
from app.bot.service import BotService
from app.db.models import BotRun, Event
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_monthly_halt_belongs_to_its_environment(db_session: AsyncSession) -> None:
    run = BotRun(
        started_at=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
        environment="DEMO",
        strategy="trend_rider_v6_4h",
        strategy_release="6.0",
        strategy_interval="4h",
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add(
        Event(
            ts=run.started_at,
            level="WARN",
            category="breaker",
            message="LONG cap",
            ref="breaker:LONG:2026-09",
            payload_json={"bot_run_id": run.id},
        )
    )
    await db_session.flush()
    service = BotService()
    states = {}
    for environment in ("DEMO", "LIVE"):
        states[environment] = await service._monthly_risk_state(
            db_session,
            environment=environment,
            snapshot_at=dt.datetime(2026, 9, 14, tzinfo=dt.UTC),
            equity=Decimal("200"),
            active_trade=None,
        )
    assert states["DEMO"].halted_long
    assert not states["LIVE"].halted_long


@pytest.mark.asyncio
async def test_unattributed_legacy_halt_remains_fail_closed(db_session: AsyncSession) -> None:
    db_session.add(
        Event(
            ts=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
            level="WARN",
            category="breaker",
            message="Legacy LONG halt",
            ref="breaker:LONG:2026-09",
            payload_json={},
        )
    )
    await db_session.flush()
    state = await BotService()._monthly_risk_state(
        db_session,
        environment="LIVE",
        snapshot_at=dt.datetime(2026, 9, 14, tzinfo=dt.UTC),
        equity=Decimal("200"),
        active_trade=None,
    )
    assert state.halted_long
