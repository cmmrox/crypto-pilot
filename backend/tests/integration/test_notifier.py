"""Integration tests for the notifier service (QA-7)."""

from __future__ import annotations

import pytest
from app.db.models import Event
from app.notifier.service import notify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeSmsGateway


@pytest.mark.asyncio
async def test_successful_send_marks_delivered(db_session: AsyncSession) -> None:
    gw = FakeSmsGateway()
    status = await notify(
        db_session,
        gw,
        kind="bot_started",
        to="94711234567",
        payload={
            "environment": "DEMO",
            "strategy": "trend_rider_v6_4h",
            "equity": "5000",
        },
    )
    await db_session.commit()
    assert status == "delivered"
    assert len(gw.sent) == 1
    ev = (await db_session.execute(select(Event).where(Event.category == "sms"))).scalars().all()
    assert ev[-1].sms_status == "delivered"


@pytest.mark.asyncio
async def test_retry_then_recover(db_session: AsyncSession) -> None:
    gw = FakeSmsGateway(fail_times=1)  # first attempt fails, second succeeds
    status = await notify(db_session, gw, kind="breaker", to="94711234567", payload={})
    assert status == "recovered"
    assert gw.attempts == 2


@pytest.mark.asyncio
async def test_exhausted_retries_never_raise(db_session: AsyncSession) -> None:
    gw = FakeSmsGateway(always_fail=True)
    status = await notify(
        db_session, gw, kind="error", to="94711234567", payload={"error": "order rejected"}
    )
    await db_session.commit()
    assert status == "failed"
    assert gw.attempts == 3  # 3 attempts then give up
    ev = (await db_session.execute(select(Event).where(Event.category == "sms"))).scalars().all()
    assert ev[-1].level == "ERROR"


@pytest.mark.asyncio
async def test_disabled_toggle_skips(db_session: AsyncSession) -> None:
    gw = FakeSmsGateway()
    status = await notify(db_session, gw, kind="trade_opened", to="x", payload={}, enabled=False)
    assert status == "disabled"
    assert gw.attempts == 0
