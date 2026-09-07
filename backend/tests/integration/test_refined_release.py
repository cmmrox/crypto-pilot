"""Real DB/API and bot execution contract for the separately selected release."""

from decimal import Decimal

import httpx
import pytest
from app.bot.service import BotService
from app.db.models import BotRun, Event, Order, Trade
from app.db.session import get_sessionmaker
from app.execution.filters import round_price
from app.execution.orders import OrderManager
from app.risk.sizing import SizingResult
from app.services.settings_store import get_settings_row
from app.strategies.base import Candle as StrategyCandle
from app.strategies.base import MoveStop, TradeState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from strategy_runtime.refined_trend_rider import RefinedTrendRider

from tests.conftest import auth_headers
from tests.fakes import FakeExchange
from tests.integration.test_bot_lifecycle import _bull_candles, _fresh_regime_index

REFINED = "trend_rider_refined_v1_4h"
D = Decimal


@pytest.mark.asyncio
async def test_selection_persists_audits_and_does_not_start_or_switch_environment(
    app_client: httpx.AsyncClient,
    owner: str,
) -> None:
    headers = await auth_headers(app_client)
    response = await app_client.put(
        "/api/settings/strategy", headers=headers, json={"name": REFINED}
    )
    assert response.status_code == 200
    listed = (await app_client.get("/api/strategies", headers=headers)).json()
    release = next(row for row in listed if row["name"] == REFINED)
    assert release["active"] is True
    assert release["params"]["trail_atr"] == 4.5
    assert release["validated_release"] == "1.0"
    async with get_sessionmaker()() as session:
        settings = await get_settings_row(session)
        assert settings.active_strategy == REFINED
        assert settings.active_environment == "DEMO"
        assert await session.scalar(select(BotRun.id)) is None
        event = await session.scalar(select(Event).where(Event.ref == "strategy_switch"))
        assert event is not None
        assert event.payload_json["to"] == REFINED
        assert event.payload_json["from"] == "trend_rider_v6_4h"
        assert event.payload_json["release"] == "1.0"
        assert event.payload_json["parameters"]["trail_atr"] == 4.5
    restored = await app_client.put(
        "/api/settings/strategy", headers=headers, json={"name": "trend_rider_v6_4h"}
    )
    assert restored.status_code == 200


@pytest.mark.asyncio
async def test_selection_cannot_override_pinned_parameters(
    app_client: httpx.AsyncClient,
    owner: str,
) -> None:
    response = await app_client.put(
        "/api/settings/strategy",
        headers=await auth_headers(app_client),
        json={"name": REFINED, "parameters": {"trail_atr": 8}},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("blocker", ["running", "open_position"])
async def test_refined_selection_refuses_unsafe_state(
    app_client: httpx.AsyncClient,
    owner: str,
    blocker: str,
) -> None:
    headers = await auth_headers(app_client)
    async with get_sessionmaker()() as session:
        if blocker == "running":
            await BotService().start(session, FakeExchange(), by="qa")
        else:
            await OrderManager(FakeExchange(mark_price=D("150")), symbol="BTCUSDT").open_long(
                session,
                sizing=SizingResult(D("1"), D("150"), D("0.03"), True, "ok"),
                stop_price=D("100"),
                tp1_price=D("160"),
                tp1_fraction=D("0.4"),
                strategy="trend_rider_v6_4h",
                strategy_release="6.0",
                strategy_interval="4h",
            )
        await session.commit()
    response = await app_client.put(
        "/api/settings/strategy", headers=headers, json={"name": REFINED}
    )
    assert response.status_code == 409
    async with get_sessionmaker()() as session:
        assert (await get_settings_row(session)).active_strategy == "trend_rider_v6_4h"
        assert await session.scalar(select(Event.id).where(Event.ref == "strategy_switch")) is None


@pytest.mark.asyncio
async def test_refined_bot_uses_selected_release_and_rejects_duplicate_candle(
    db_session: AsyncSession,
) -> None:
    (await get_settings_row(db_session)).active_strategy = REFINED
    service = BotService()
    candles = _bull_candles(320)
    fresh = _fresh_regime_index(candles)
    exchange = FakeExchange(mark_price=candles[fresh].close)
    orders = OrderManager(exchange, symbol="BTCUSDT")
    run = await service.start(db_session, exchange, by="qa")
    assert (run.strategy, run.strategy_release, run.strategy_interval) == (REFINED, "1.0", "4h")
    actions = await service.evaluate_once(
        db_session, exchange, orders, candles=candles[: fresh + 1]
    )
    assert "open_long" in actions
    trade = await db_session.scalar(select(Trade))
    assert trade is not None
    assert (trade.strategy, trade.strategy_release) == (REFINED, "1.0")
    assert (
        await db_session.scalar(
            select(Order.id).where(
                Order.trade_id == trade.id, Order.type == "STOP_MARKET", Order.status == "NEW"
            )
        )
        is not None
    )
    previous_orders = len(exchange.placed)
    assert (
        await service.evaluate_once(db_session, exchange, orders, candles=candles[: fresh + 1])
        == []
    )
    assert len(exchange.placed) == previous_orders


@pytest.mark.asyncio
async def test_refined_tp_fill_ratchets_to_exact_strategy_stop_in_safe_mode(
    db_session: AsyncSession,
) -> None:
    (await get_settings_row(db_session)).active_strategy = REFINED
    service = BotService()
    exchange = FakeExchange(mark_price=D("150"), balance=D("5000"))
    manager = OrderManager(exchange, symbol="BTCUSDT")
    await service.start(db_session, exchange, by="qa")
    trade = await manager.open_long(
        db_session,
        sizing=SizingResult(D("1"), D("150"), D("0.03"), True, "ok"),
        stop_price=D("100"),
        tp1_price=D("160"),
        tp1_fraction=D("0.4"),
        strategy=REFINED,
        strategy_release="1.0",
        strategy_interval="4h",
    )
    tp = (
        await db_session.execute(
            select(Order).where(Order.trade_id == trade.id, Order.type == "LIMIT")
        )
    ).scalar_one()
    exchange.fill_resting(tp.client_order_id, price=D("160"))
    await service.enter_safe_mode(db_session, reason="QA: management must continue")
    candles = _bull_candles(320)
    exchange.mark = candles[-1].close
    actions = await service.evaluate_once(db_session, exchange, manager, candles=candles)
    assert "move_stop" in actions
    assert trade.remaining_qty == D("0.6")
    assert trade.highest_high is not None
    expected = RefinedTrendRider().on_candle(
        [
            StrategyCandle(
                int(c.open_time.timestamp() * 1000),
                float(c.open),
                float(c.high),
                float(c.low),
                float(c.close),
                float(c.volume),
            )
            for c in candles
        ],
        TradeState(
            equity=5000,
            long_position=True,
            tp1_done=True,
            long_entry=150,
            long_stop=100,
            highest_high=float(trade.highest_high),
        ),
    )
    assert len(expected) == 1 and isinstance(expected[0], MoveStop)
    tick = (await exchange.get_filters("BTCUSDT")).tick_size
    expected_stop = round_price(D(str(expected[0].price)), tick)
    stop = (
        await db_session.execute(
            select(Order).where(
                Order.trade_id == trade.id, Order.type == "STOP_MARKET", Order.status == "NEW"
            )
        )
    ).scalar_one()
    assert stop.stop_price == expected_stop
