"""Integration tests for the OrderManager + Reconciler against a FakeExchange (QA-4).

These verify the execution logic deterministically without network/credentials;
a live DEMO round-trip test validates the real adapter separately.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.db.models import Event, Order, Trade
from app.execution.orders import (
    OrderManager,
    ProtectiveStopFailed,
    new_client_order_id,
    persist_emergency_exit,
)
from app.execution.reconcile import reconcile_position
from app.risk.sizing import size_by_risk, size_long, size_short
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeExchange

D = Decimal
AMPLE_MARGIN = Decimal("1000000")


async def _filters(ex: FakeExchange):
    return await ex.get_filters("BTCUSDT")


@pytest.mark.asyncio
async def test_open_long_places_entry_stop_and_tp(db_session: AsyncSession) -> None:
    ex = FakeExchange(mark_price=D("65000"))
    om = OrderManager(ex, symbol="BTCUSDT")
    sizing = size_long(
        equity=D("5000"),
        risk_pct=D("2"),
        stop_distance=D("2000"),
        price=D("65000"),
        leverage_cap=D("3"),
        available_margin=AMPLE_MARGIN,
        filters=await _filters(ex),
    )
    trade = await om.open_long(
        db_session,
        sizing=sizing,
        stop_price=D("63000"),
        tp1_price=D("67000"),
        tp1_fraction=D("0.4"),
        strategy="trend_rider_v6_4h",
        strategy_release="6.0",
        strategy_interval="4h",
    )
    await db_session.commit()
    # Entry + stop + TP1 were placed.
    types = [t[0] for t in ex.placed]
    assert types == ["MARKET", "STOP_MARKET", "LIMIT"]
    # Persisted a trade and three orders.
    result = await db_session.execute(select(Order).where(Order.trade_id == trade.id))
    orders = result.scalars().all()
    assert len(orders) == 3
    assert trade.side == "LONG"


@pytest.mark.asyncio
async def test_open_long_emergency_flattens_when_stop_fails(
    db_session: AsyncSession,
) -> None:
    class StopFailingExchange(FakeExchange):
        async def place_stop_market(
            self,
            symbol,
            side,
            qty,
            stop_price,
            *,
            client_order_id,
            reduce_only=True,
        ):
            raise RuntimeError("simulated stop rejection")

    ex = StopFailingExchange(mark_price=D("65000"))
    om = OrderManager(ex, symbol="BTCUSDT")
    sizing = size_long(
        equity=D("5000"),
        risk_pct=D("2"),
        stop_distance=D("2000"),
        price=D("65000"),
        leverage_cap=D("3"),
        available_margin=AMPLE_MARGIN,
        filters=await _filters(ex),
    )
    with pytest.raises(ProtectiveStopFailed, match="emergency-flattened") as excinfo:
        await om.open_long(
            db_session,
            sizing=sizing,
            stop_price=D("63000"),
            tp1_price=D("67000"),
            tp1_fraction=D("0.4"),
            strategy="trend_rider_v6_4h",
            strategy_release="6.0",
            strategy_interval="4h",
        )
    assert (await ex.get_position("BTCUSDT")).qty == D("0")
    record = excinfo.value.record
    assert record.flattened is True
    assert record.stop_error == "simulated stop rejection"

    # Mirror the trading loop: it rolls back the poisoned decision transaction and
    # then durably records the fills that really executed (audit trail, BSD G5).
    await db_session.rollback()
    await persist_emergency_exit(db_session, record)
    await db_session.commit()

    trades = (await db_session.execute(select(Trade))).scalars().all()
    assert len(trades) == 1
    assert trades[0].closed_at is not None  # recorded net-flat
    assert trades[0].exit_reason == "protective_stop_failed_emergency_exit"
    orders = (
        (await db_session.execute(select(Order).where(Order.trade_id == trades[0].id)))
        .scalars()
        .all()
    )
    assert len(orders) == 2  # entry MARKET + emergency reduce-only MARKET
    events = (
        (await db_session.execute(select(Event).where(Event.ref == f"trade:{trades[0].id}")))
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].payload_json["stop_error"] == "simulated stop rejection"
    assert events[0].payload_json["flattened"] is True


@pytest.mark.asyncio
async def test_open_long_records_open_trade_when_flatten_also_fails(
    db_session: AsyncSession,
) -> None:
    """Stop fails AND the emergency flatten fails: the entry is recorded as an
    OPEN trade so the next reconciliation treats the position as possibly held."""

    class FullyFailingExchange(FakeExchange):
        async def place_stop_market(
            self, symbol, side, qty, stop_price, *, client_order_id, reduce_only=True
        ):
            raise RuntimeError("simulated stop rejection")

        async def place_market(self, symbol, side, qty, *, client_order_id, reduce_only=False):
            if reduce_only:
                raise RuntimeError("simulated flatten rejection")
            return await super().place_market(
                symbol, side, qty, client_order_id=client_order_id, reduce_only=reduce_only
            )

    ex = FullyFailingExchange(mark_price=D("65000"))
    om = OrderManager(ex, symbol="BTCUSDT")
    sizing = size_long(
        equity=D("5000"),
        risk_pct=D("2"),
        stop_distance=D("2000"),
        price=D("65000"),
        leverage_cap=D("3"),
        available_margin=AMPLE_MARGIN,
        filters=await _filters(ex),
    )
    with pytest.raises(ProtectiveStopFailed, match="not confirmed") as excinfo:
        await om.open_long(
            db_session,
            sizing=sizing,
            stop_price=D("63000"),
            tp1_price=D("67000"),
            tp1_fraction=D("0.4"),
            strategy="trend_rider_v6_4h",
            strategy_release="6.0",
            strategy_interval="4h",
        )
    record = excinfo.value.record
    assert record.flattened is False

    await db_session.rollback()
    await persist_emergency_exit(db_session, record)
    await db_session.commit()

    trades = (await db_session.execute(select(Trade))).scalars().all()
    assert len(trades) == 1
    assert trades[0].closed_at is None  # left open: position may be unprotected
    assert trades[0].exit_reason == "protective_stop_failed_flatten_unconfirmed"
    orders = (
        (await db_session.execute(select(Order).where(Order.trade_id == trades[0].id)))
        .scalars()
        .all()
    )
    assert len(orders) == 1  # only the entry executed; no confirmed exit


@pytest.mark.asyncio
async def test_open_short_has_no_price_stop(db_session: AsyncSession) -> None:
    ex = FakeExchange(mark_price=D("60000"))
    om = OrderManager(ex, symbol="BTCUSDT")
    sizing = size_short(
        equity=D("5000"),
        weight_pct=D("75"),
        vol_target=D("0.40"),
        realized_vol=D("0.40"),
        price=D("60000"),
        leverage_cap=D("3"),
        available_margin=AMPLE_MARGIN,
        filters=await _filters(ex),
    )
    trade = await om.open_short(
        db_session,
        sizing=sizing,
        strategy="trend_rider_v6_4h",
        strategy_release="6.0",
        strategy_interval="4h",
    )
    await db_session.commit()
    # Only a MARKET entry — no STOP_MARKET by validated design.
    assert [t[0] for t in ex.placed] == ["MARKET"]
    assert not any(t[0] == "STOP_MARKET" for t in ex.placed)
    assert trade.side == "SHORT"


@pytest.mark.asyncio
async def test_idempotent_client_order_id(db_session: AsyncSession) -> None:
    ex = FakeExchange()
    cid = new_client_order_id("CPL")
    r1 = await ex.place_market("BTCUSDT", "BUY", D("0.01"), client_order_id=cid)
    r2 = await ex.place_market("BTCUSDT", "BUY", D("0.01"), client_order_id=cid)
    # The duplicate does not create a second fill.
    assert r1.status == "FILLED"
    assert r2.exchange_order_id == "DUP"
    pos = await ex.get_position("BTCUSDT")
    assert pos.qty == D("0.01")  # only one fill applied


@pytest.mark.asyncio
async def test_reconcile_matches_and_mismatches(db_session: AsyncSession) -> None:
    ex = FakeExchange(mark_price=D("65000"))
    await ex.place_market("BTCUSDT", "SELL", D("0.05"), client_order_id="x")  # short 0.05
    ok = await reconcile_position(ex, "BTCUSDT", expected_qty=D("-0.05"))
    assert ok.matched
    bad = await reconcile_position(ex, "BTCUSDT", expected_qty=D("0.10"))
    assert not bad.matched
    assert "mismatch" in bad.detail


@pytest.mark.asyncio
async def test_flatten_cancels_and_closes(db_session: AsyncSession) -> None:
    ex = FakeExchange(mark_price=D("65000"))
    await ex.place_market("BTCUSDT", "BUY", D("0.1"), client_order_id="e")
    await ex.place_stop_market("BTCUSDT", "SELL", D("0.1"), D("63000"), client_order_id="s")
    om = OrderManager(ex, symbol="BTCUSDT")
    await om.flatten(db_session, side="LONG", qty=D("0.1"), reason="test")
    await db_session.commit()
    pos = await ex.get_position("BTCUSDT")
    assert pos.qty == D("0")  # flattened
    assert len(await ex.get_open_orders("BTCUSDT")) == 0  # stop cancelled


@pytest.mark.asyncio
async def test_flatten_sends_trade_closed_notification(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import notify_config

    sent: list[tuple[str, dict[str, object]]] = []

    async def capture(
        _session: AsyncSession,
        *,
        kind: str,
        payload: dict[str, object],
    ) -> str:
        sent.append((kind, payload))
        return "delivered"

    monkeypatch.setattr(notify_config, "notify_event", capture)
    ex = FakeExchange(mark_price=D("65000"))
    om = OrderManager(ex, symbol="BTCUSDT", environment="LIVE")
    sizing = size_short(
        equity=D("5000"),
        weight_pct=D("10"),
        vol_target=D("0.20"),
        realized_vol=D("0.20"),
        price=D("65000"),
        leverage_cap=D("6"),
        available_margin=AMPLE_MARGIN,
        filters=await _filters(ex),
    )
    trade = await om.open_short(
        db_session,
        sizing=sizing,
        strategy="trend_rider_v6_4h",
        strategy_release="6.0",
        strategy_interval="4h",
    )

    await om.flatten(
        db_session,
        side="SHORT",
        qty=trade.remaining_qty,
        reason="Stage 12 dust verification",
    )

    assert [kind for kind, _payload in sent] == ["short_opened", "trade_closed"]
    assert sent[-1][1]["side"] == "SHORT"
    assert sent[-1][1]["reason"] == "Stage 12 dust verification"


@pytest.mark.asyncio
async def test_kill_switch_flattens_from_short(db_session: AsyncSession) -> None:
    ex = FakeExchange(mark_price=D("60000"))
    await ex.place_market("BTCUSDT", "SELL", D("0.08"), client_order_id="e")
    await ex.place_take_profit("BTCUSDT", "BUY", D("0.08"), D("55000"), client_order_id="t")
    om = OrderManager(ex, symbol="BTCUSDT")
    await om.kill(db_session)
    await db_session.commit()
    assert (await ex.get_position("BTCUSDT")).qty == D("0")
    assert len(await ex.get_open_orders("BTCUSDT")) == 0


@pytest.mark.asyncio
async def test_order_rows_store_decimal_and_client_id(db_session: AsyncSession) -> None:
    ex = FakeExchange(mark_price=D("65000"))
    om = OrderManager(ex, symbol="BTCUSDT")
    sizing = size_long(
        equity=D("5000"),
        risk_pct=D("2"),
        stop_distance=D("2000"),
        price=D("65000"),
        leverage_cap=D("3"),
        available_margin=AMPLE_MARGIN,
        filters=await _filters(ex),
    )
    await om.open_long(
        db_session,
        sizing=sizing,
        stop_price=D("63000"),
        tp1_price=D("67000"),
        tp1_fraction=D("0.4"),
        strategy="trend_rider_v6_4h",
        strategy_release="6.0",
        strategy_interval="4h",
    )
    await db_session.commit()
    orders = (await db_session.execute(select(Order))).scalars().all()
    for o in orders:
        assert o.client_order_id  # every order has an idempotent client id
        assert isinstance(o.qty, Decimal)


@pytest.mark.asyncio
async def test_long_stop_ratchets_and_never_lowers(db_session: AsyncSession) -> None:
    ex = FakeExchange(mark_price=D("65000"))
    om = OrderManager(ex, symbol="BTCUSDT")
    sizing = size_long(
        equity=D("5000"),
        risk_pct=D("2"),
        stop_distance=D("2000"),
        price=D("65000"),
        leverage_cap=D("3"),
        available_margin=AMPLE_MARGIN,
        filters=await _filters(ex),
    )
    trade = await om.open_long(
        db_session,
        sizing=sizing,
        stop_price=D("63000"),
        tp1_price=D("67000"),
        tp1_fraction=D("0.4"),
        strategy="trend_rider_v6_4h",
        strategy_release="6.0",
        strategy_interval="4h",
    )

    moved = await om.move_long_stop(
        db_session,
        trade=trade,
        new_stop_price=D("64000"),
        remaining_qty=trade.remaining_qty,
        filters=await _filters(ex),
    )
    lowered = await om.move_long_stop(
        db_session,
        trade=trade,
        new_stop_price=D("63500"),
        remaining_qty=trade.remaining_qty,
        filters=await _filters(ex),
    )

    assert moved is True
    assert lowered is False
    active = [
        row for row in await ex.get_open_orders("BTCUSDT") if row.client_order_id.startswith("CPS")
    ]
    assert len(active) == 1


@pytest.mark.asyncio
async def test_short_resize_increases_and_reduces_to_exact_target(
    db_session: AsyncSession,
) -> None:
    ex = FakeExchange(mark_price=D("60000"))
    om = OrderManager(ex, symbol="BTCUSDT")
    sizing = size_short(
        equity=D("5000"),
        weight_pct=D("75"),
        vol_target=D("0.40"),
        realized_vol=D("0.40"),
        price=D("60000"),
        leverage_cap=D("3"),
        available_margin=AMPLE_MARGIN,
        filters=await _filters(ex),
    )
    trade = await om.open_short(
        db_session,
        sizing=sizing,
        strategy="trend_rider_v6_4h",
        strategy_release="6.0",
        strategy_interval="4h",
    )

    increased = trade.remaining_qty + D("0.001")
    assert await om.resize_short(
        db_session,
        trade=trade,
        current_qty=-trade.remaining_qty,
        target_qty=increased,
    )
    reduced = increased - D("0.002")
    assert await om.resize_short(
        db_session,
        trade=trade,
        current_qty=-increased,
        target_qty=reduced,
    )

    assert (await ex.get_position("BTCUSDT")).qty == -reduced
    assert trade.remaining_qty == reduced


# --- stop-protected short book (Atlas 7 Dual / EnterShortStop) ---


@pytest.mark.asyncio
async def test_open_short_with_stop_places_entry_stop_and_tp(db_session: AsyncSession) -> None:
    ex = FakeExchange(mark_price=D("65000"))
    om = OrderManager(ex, symbol="BTCUSDT")
    sizing = size_by_risk(
        equity=D("5000"),
        risk_pct=D("4"),
        stop_distance=D("2000"),
        price=D("65000"),
        leverage_cap=D("3"),
        available_margin=AMPLE_MARGIN,
        filters=await _filters(ex),
    )
    trade = await om.open_short_with_stop(
        db_session,
        sizing=sizing,
        stop_price=D("67000"),
        tp1_price=D("61000"),
        tp1_fraction=D("0.4"),
        strategy="atlas_dual_v1_4h",
        strategy_release="1.0",
        strategy_interval="4h",
    )
    await db_session.commit()
    assert [t[0] for t in ex.placed] == ["MARKET", "STOP_MARKET", "LIMIT"]
    # The protective stop buys back above the entry; the target buys back below it.
    assert [t[1] for t in ex.placed] == ["SELL", "BUY", "BUY"]
    assert trade.side == "SHORT"
    assert trade.lowest_low == trade.entry_px
    stop = (
        await db_session.execute(
            select(Order).where(Order.trade_id == trade.id, Order.type == "STOP_MARKET")
        )
    ).scalar_one()
    assert stop.stop_price == D("67000")
    assert stop.reduce_only is True
    tp = (
        await db_session.execute(
            select(Order).where(Order.trade_id == trade.id, Order.type == "LIMIT")
        )
    ).scalar_one()
    assert tp.price == D("61000")
    assert tp.qty == sizing.qty * D("0.4")


@pytest.mark.asyncio
async def test_open_short_with_stop_emergency_flattens_when_stop_fails(
    db_session: AsyncSession,
) -> None:
    class RejectingStops(FakeExchange):
        async def place_stop_market(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("binance -2021: order would immediately trigger")

    ex = RejectingStops(mark_price=D("65000"))
    om = OrderManager(ex, symbol="BTCUSDT")
    sizing = size_by_risk(
        equity=D("5000"),
        risk_pct=D("4"),
        stop_distance=D("2000"),
        price=D("65000"),
        leverage_cap=D("3"),
        available_margin=AMPLE_MARGIN,
        filters=await _filters(ex),
    )
    with pytest.raises(ProtectiveStopFailed) as raised:
        await om.open_short_with_stop(
            db_session,
            sizing=sizing,
            stop_price=D("67000"),
            tp1_price=D("61000"),
            tp1_fraction=D("0.4"),
            strategy="atlas_dual_v1_4h",
            strategy_release="1.0",
            strategy_interval="4h",
        )
    record = raised.value.record
    assert record.side == "SHORT"
    assert record.flattened is True
    assert (await ex.get_position("BTCUSDT")).qty == 0  # never left unprotected
    await db_session.rollback()
    await persist_emergency_exit(db_session, record)
    await db_session.commit()
    trade = (await db_session.execute(select(Trade))).scalar_one()
    assert trade.side == "SHORT"
    assert trade.exit_reason == "protective_stop_failed_emergency_exit"


@pytest.mark.asyncio
async def test_short_stop_ratchets_down_and_never_raises(db_session: AsyncSession) -> None:
    ex = FakeExchange(mark_price=D("65000"))
    om = OrderManager(ex, symbol="BTCUSDT")
    filters = await _filters(ex)
    sizing = size_by_risk(
        equity=D("5000"),
        risk_pct=D("4"),
        stop_distance=D("2000"),
        price=D("65000"),
        leverage_cap=D("3"),
        available_margin=AMPLE_MARGIN,
        filters=filters,
    )
    trade = await om.open_short_with_stop(
        db_session,
        sizing=sizing,
        stop_price=D("67000"),
        tp1_price=D("61000"),
        tp1_fraction=D("0.4"),
        strategy="atlas_dual_v1_4h",
        strategy_release="1.0",
        strategy_interval="4h",
    )
    await db_session.flush()
    lowered = await om.move_short_stop(
        db_session,
        trade=trade,
        new_stop_price=D("64000"),
        remaining_qty=sizing.qty,
        filters=filters,
    )
    assert lowered is True
    raised_again = await om.move_short_stop(
        db_session,
        trade=trade,
        new_stop_price=D("66000"),  # would widen the risk
        remaining_qty=sizing.qty,
        filters=filters,
    )
    assert raised_again is False
    active = (
        (
            await db_session.execute(
                select(Order).where(
                    Order.trade_id == trade.id,
                    Order.type == "STOP_MARKET",
                    Order.status.in_(("NEW", "PARTIALLY_FILLED")),
                )
            )
        )
        .scalars()
        .all()
    )
    assert [order.stop_price for order in active] == [D("64000")]
