"""Integration tests for the trades + monthly APIs (QA-6)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import httpx
import pytest
from app.db.models import Order, Trade
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.conftest import auth_headers

D = Decimal


async def _headers(client: httpx.AsyncClient, _secret: str) -> dict[str, str]:
    return await auth_headers(client)


async def _seed_trades() -> None:
    import os

    engine = create_async_engine(os.environ["CP_DATABASE_URL"])
    async with AsyncSession(engine) as s:
        # A winning long and a losing short, both closed in 2026-07.
        t1 = Trade(
            opened_at=dt.datetime(2026, 7, 5, tzinfo=dt.UTC),
            closed_at=dt.datetime(2026, 7, 6, tzinfo=dt.UTC),
            side="LONG",
            entry_px=D("60000"),
            exit_px=D("62000"),
            qty=D("0.01"),
            fees=D("5"),
            realized_pnl=D("200"),
            r_multiple=D("1.5"),
            exit_reason="4 ATR trail",
            strategy="trend_rider_v6",
            environment="DEMO",
        )
        t2 = Trade(
            opened_at=dt.datetime(2026, 7, 10, tzinfo=dt.UTC),
            closed_at=dt.datetime(2026, 7, 11, tzinfo=dt.UTC),
            side="SHORT",
            entry_px=D("61000"),
            exit_px=D("61500"),
            qty=D("0.01"),
            fees=D("4"),
            realized_pnl=D("-50"),
            r_multiple=D("-0.5"),
            exit_reason="bear regime ended",
            strategy="trend_rider_v6",
            environment="DEMO",
        )
        s.add_all([t1, t2])
        await s.flush()
        s.add(
            Order(
                client_order_id="CPL-1",
                trade_id=t1.id,
                type="MARKET",
                status="FILLED",
                qty=D("0.01"),
                reduce_only=False,
            )
        )
        s.add(
            Order(
                client_order_id="CPS-1",
                trade_id=t1.id,
                type="STOP_MARKET",
                status="NEW",
                qty=D("0.01"),
                stop_price=D("58500"),
                reduce_only=True,
            )
        )
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_trades_requires_auth(app_client: httpx.AsyncClient, owner: str) -> None:
    assert (await app_client.get("/api/trades")).status_code == 401


@pytest.mark.asyncio
async def test_list_and_filter_trades(app_client: httpx.AsyncClient, owner: str) -> None:
    await _seed_trades()
    h = await _headers(app_client, owner)
    all_trades = (await app_client.get("/api/trades", headers=h)).json()
    assert len(all_trades) == 2
    longs = (await app_client.get("/api/trades?side=LONG", headers=h)).json()
    assert len(longs) == 1 and longs[0]["side"] == "LONG"
    assert longs[0]["outcome"] == "WIN"
    shorts = (await app_client.get("/api/trades?side=SHORT", headers=h)).json()
    assert shorts[0]["outcome"] == "LOSS"
    julys = (await app_client.get("/api/trades?month=2026-07", headers=h)).json()
    assert len(julys) == 2


@pytest.mark.asyncio
async def test_trade_detail_has_orders(app_client: httpx.AsyncClient, owner: str) -> None:
    await _seed_trades()
    h = await _headers(app_client, owner)
    trades = (await app_client.get("/api/trades?side=LONG", headers=h)).json()
    detail = (await app_client.get(f"/api/trades/{trades[0]['id']}", headers=h)).json()
    assert len(detail["orders"]) == 2
    assert any(o["type"] == "STOP_MARKET" for o in detail["orders"])


@pytest.mark.asyncio
async def test_csv_export_matches_db(app_client: httpx.AsyncClient, owner: str) -> None:
    await _seed_trades()
    h = await _headers(app_client, owner)
    resp = await app_client.get("/api/trades/export.csv", headers=h)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    body = resp.text
    assert "realized_pnl" in body  # header
    assert "200" in body and "-50" in body  # both trades' pnl


@pytest.mark.asyncio
async def test_monthly_ledger_aggregates(app_client: httpx.AsyncClient, owner: str) -> None:
    await _seed_trades()
    h = await _headers(app_client, owner)
    ledger = (await app_client.get("/api/monthly", headers=h)).json()
    july = next(m for m in ledger if m["month"] == "2026-07")
    assert july["trades"] == 2
    assert Decimal(july["realized_pnl"]) == D("150")  # 200 - 50
    assert Decimal(july["fees"]) == D("9")  # 5 + 4
    assert Decimal(july["net"]) == D("141")  # 150 - 9
    # Withdrawable = 10% of positive net = 14.10
    assert Decimal(july["withdrawable"]) == D("14.10")


@pytest.mark.asyncio
async def test_mark_withdrawn_idempotent(app_client: httpx.AsyncClient, owner: str) -> None:
    await _seed_trades()
    h = await _headers(app_client, owner)
    r1 = await app_client.post("/api/monthly/mark-withdrawn", json={"month": "2026-07"}, headers=h)
    assert r1.status_code == 200
    ledger = (await app_client.get("/api/monthly", headers=h)).json()
    july = next(m for m in ledger if m["month"] == "2026-07")
    assert Decimal(july["withdrawn"]) == D("14.10")
    assert Decimal(july["withdrawable"]) == D("0")  # already withdrawn
    r2 = await app_client.post("/api/monthly/mark-withdrawn", json={"month": "2026-07"}, headers=h)
    assert "already" in r2.json()["message"]
