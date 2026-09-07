"""Integration contract for the owner command-center projection."""

from __future__ import annotations

import datetime as dt
import os
from decimal import Decimal

import httpx
import pytest
from app.db.models import Briefing, Candle, Event
from app.execution.binance_client import MarkPrice, Ticker24h
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_overview_combines_market_watch_news_and_operations(
    app_client: httpx.AsyncClient,
    owner: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del owner
    headers = await auth_headers(app_client)
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    start = now - dt.timedelta(hours=4 * 240)
    engine = create_async_engine(os.environ["CP_DATABASE_URL"])
    async with AsyncSession(engine) as session:
        session.add_all(
            [
                Candle(
                    symbol="BTCUSDT",
                    interval="4h",
                    open_time=start + dt.timedelta(hours=4 * index),
                    open=Decimal(50_000 + index * 20 - 1),
                    high=Decimal(50_000 + index * 20 + 10),
                    low=Decimal(50_000 + index * 20 - 10),
                    close=Decimal(50_000 + index * 20),
                    volume=Decimal("100"),
                    closed=True,
                )
                for index in range(240)
            ]
        )
        session.add(
            Event(
                ts=now - dt.timedelta(minutes=1),
                level="INFO",
                category="system",
                message="Reconciliation completed",
                payload_json={},
                ref="reconcile",
            )
        )
        session.add(
            Briefing(
                briefing_date=now.date(),
                model="test-model",
                bullets=[{"text": "ETF flows remain constructive.", "source": "Test Wire"}],
                sentiment="Cautiously constructive",
                generated_at=now,
            )
        )
        await session.commit()
    await engine.dispose()

    async def mark_price(_client: object, symbol: str) -> MarkPrice:
        return MarkPrice(
            symbol=symbol,
            price=Decimal("117742.84233695"),
            observed_at_ms=int(now.timestamp() * 1000),
        )

    async def ticker(_client: object, symbol: str) -> Ticker24h:
        return Ticker24h(symbol=symbol, price_change_percent=Decimal("1.27"))

    monkeypatch.setattr(
        "app.execution.binance_client.BinanceClient.get_mark_price",
        mark_price,
    )
    monkeypatch.setattr(
        "app.execution.binance_client.BinanceClient.get_ticker_24h",
        ticker,
    )

    response = await app_client.get("/api/overview", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["strategy"] == "trend_rider_v6_4h"
    assert body["strategy_display_name"] == "Atlas 6 · 4h"

    assert body["market"]["symbol"] == "BTCUSDT"
    assert body["market"]["interval"] == "4h"
    assert body["market"]["mark_price"] == "117742.84233695"
    assert body["market"]["price_change_24h_pct"] == "1.27"
    assert len(body["market"]["sparkline"]) == 24
    assert isinstance(body["market"]["sparkline"][0]["normalized_bps"], int)
    assert body["watch"]["available"] is True
    assert {rule["key"] for rule in body["watch"]["rules"]} == {
        "long_regime",
        "pullback_resume",
        "deep_bear_short",
    }
    assert "not a guaranteed trade" in body["watch"]["disclaimer"]
    assert body["briefing"]["bullets"][0]["source"] == "Test Wire"
    assert "never a trading input" in body["briefing"]["isolation_notice"]
    assert any(item["label"] == "Reconciliation completed" for item in body["activity"])
    assert {"worker_healthy", "heartbeat_at", "candle_gaps"} <= body["engine"].keys()
