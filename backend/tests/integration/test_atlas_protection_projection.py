"""Overview protection comes from exchange order truth for either position side."""

from contextlib import asynccontextmanager
from dataclasses import replace
from decimal import Decimal as D

import pytest
from app.execution.orders import OrderManager
from app.risk.sizing import SizingResult
from app.services.overview_service import _account_snapshot
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeExchange


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
async def test_overview_projects_confirmed_protection_for_both_sides(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    side: str,
) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    manager = OrderManager(exchange, "BTCUSDT")
    enter = manager.open_long if side == "LONG" else manager.open_short_with_stop
    await enter(
        db_session,
        sizing=SizingResult(D("0.004"), D("240"), D("1"), True, "ok"),
        stop_price=D("59000") if side == "LONG" else D("61000"),
        tp1_price=D("62000") if side == "LONG" else D("58000"),
        tp1_fraction=D("0.4"),
        strategy="atlas_dual_v1_4h",
        strategy_release="1.2",
        strategy_interval="4h",
    )
    await db_session.commit()

    async def credentials(*args, **kwargs):
        return "qa-public-id", "qa-placeholder"

    @asynccontextmanager
    async def client(*args, **kwargs):
        yield None

    async def order_truth(_symbol):
        rows = []
        for item in exchange._open_orders.values():
            is_stop = item.client_order_id.startswith("CPS-")
            rows.append(
                replace(
                    item,
                    raw={
                        **item.raw,
                        "side": "SELL" if side == "LONG" else "BUY",
                        "reduceOnly": True,
                        "type": "STOP_MARKET" if is_stop else "LIMIT",
                        "origQty": "0.004" if is_stop else "0.0016",
                        "stopPrice": str(exchange.price_by_order[item.client_order_id])
                        if is_stop
                        else "0",
                        "price": str(exchange.price_by_order[item.client_order_id])
                        if not is_stop
                        else "0",
                    },
                )
            )
        return rows

    monkeypatch.setattr("app.services.overview_service.cred_svc.get_decrypted", credentials)
    monkeypatch.setattr("app.services.overview_service.console_client", client)
    monkeypatch.setattr("app.services.overview_service.BinanceExchange", lambda _: exchange)
    monkeypatch.setattr(exchange, "get_open_orders", order_truth)
    snapshot = await _account_snapshot(db_session, "DEMO", "BTCUSDT")
    assert snapshot.position is not None
    position = snapshot.position
    assert position.has_price_stop and position.protection_confirmed
    assert position.stop_policy == "required" and position.stop_working_type == "CONTRACT_PRICE"
    assert position.stop_price == ("59000" if side == "LONG" else "61000")
    assert D(position.tp1_qty) == D("0.0016") and position.tp1_percent == "40.00"
    assert position.stop_status == "NEW" and position.tp1_status == "NEW"
