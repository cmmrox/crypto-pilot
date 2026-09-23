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


async def _seed_trades(total: int = 2) -> None:
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
            strategy="trend_rider_v6_4h",
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
            strategy="trend_rider_v6_4h",
            environment="DEMO",
        )
        extra = [
            Trade(
                opened_at=dt.datetime(2026, 7, 12, tzinfo=dt.UTC) + dt.timedelta(minutes=i),
                closed_at=dt.datetime(2026, 7, 13, tzinfo=dt.UTC) + dt.timedelta(minutes=i),
                side="LONG",
                entry_px=D("60000"),
                exit_px=D("60100"),
                qty=D("0.01"),
                fees=D("1"),
                realized_pnl=D("1"),
                r_multiple=D("0.1"),
                exit_reason=f"pagination fixture {i}",
                strategy="trend_rider_v6_4h",
                environment="DEMO",
            )
            for i in range(total - 2)
        ]
        s.add_all([t1, t2, *extra])
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
    assert all_trades["total"] == 2
    assert len(all_trades["items"]) == 2
    longs = (await app_client.get("/api/trades?side=LONG", headers=h)).json()
    assert len(longs["items"]) == 1 and longs["items"][0]["side"] == "LONG"
    assert longs["items"][0]["outcome"] == "WIN"
    shorts = (await app_client.get("/api/trades?side=SHORT", headers=h)).json()
    assert shorts["items"][0]["outcome"] == "LOSS"
    julys = (await app_client.get("/api/trades?month=2026-07", headers=h)).json()
    assert len(julys["items"]) == 2


@pytest.mark.asyncio
async def test_trade_detail_has_orders(app_client: httpx.AsyncClient, owner: str) -> None:
    await _seed_trades()
    h = await _headers(app_client, owner)
    trades = (await app_client.get("/api/trades?side=LONG", headers=h)).json()
    detail = (await app_client.get(f"/api/trades/{trades['items'][0]['id']}", headers=h)).json()
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
async def test_trades_are_paginated_at_fifty_rows(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    await _seed_trades(total=55)
    headers = await _headers(app_client, owner)

    first = (await app_client.get("/api/trades?page=1&page_size=50", headers=headers)).json()
    second = (await app_client.get("/api/trades?page=2&page_size=50", headers=headers)).json()

    assert first["total"] == 55
    assert first["total_pages"] == 2
    assert len(first["items"]) == 50
    assert len(second["items"]) == 5
    assert {row["id"] for row in first["items"]}.isdisjoint(row["id"] for row in second["items"])


@pytest.mark.asyncio
async def test_trade_pagination_and_filters_are_bounded(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    headers = await _headers(app_client, owner)
    assert (await app_client.get("/api/trades?page_size=51", headers=headers)).status_code == 422
    assert (await app_client.get("/api/trades?month=2026-13", headers=headers)).status_code == 422
    assert (
        await app_client.get(f"/api/trades?search={'x' * 101}", headers=headers)
    ).status_code == 422


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


@pytest.mark.asyncio
async def test_monthly_ledger_buckets_months_in_utc(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    """A database whose default time zone is not UTC must not move a trade to another month.

    Production shares its Postgres server with other applications, so the server's
    default time zone is not ours to assume. 2026-08-31 20:00 UTC is already
    2026-09-01 01:30 in Asia/Colombo.
    """
    import os

    from app.db.session import dispose_engine
    from sqlalchemy import text

    admin = create_async_engine(os.environ["CP_DATABASE_URL"], isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        database = (await conn.execute(text("select current_database()"))).scalar_one()
        await conn.execute(text(f"ALTER DATABASE \"{database}\" SET timezone TO 'Asia/Colombo'"))
    try:
        await dispose_engine()  # reconnect so the app's sessions inherit the new default
        async with AsyncSession(admin) as s:
            s.add(
                Trade(
                    side="LONG",
                    entry_px=D("60000"),
                    exit_px=D("61000"),
                    qty=D("0.01"),
                    fees=D("1"),
                    realized_pnl=D("10"),
                    r_multiple=D("0.5"),
                    opened_at=dt.datetime(2026, 8, 31, 20, 0, tzinfo=dt.UTC),
                    closed_at=dt.datetime(2026, 9, 1, 8, 0, tzinfo=dt.UTC),
                    exit_reason="month boundary fixture",
                    strategy="trend_rider_v6_4h",
                    environment="DEMO",
                )
            )
            await s.commit()
        h = await _headers(app_client, owner)
        ledger = (await app_client.get("/api/monthly", headers=h)).json()
        assert [row["month"] for row in ledger] == ["2026-08"], ledger
        withdrawal = await app_client.post(
            "/api/monthly/mark-withdrawn", json={"month": "2026-08"}, headers=h
        )
        assert withdrawal.status_code == 200
        assert "0.90" in withdrawal.json()["message"]  # 10% of (10 - 1)
    finally:
        async with admin.connect() as conn:
            await conn.execute(text(f'ALTER DATABASE "{database}" RESET timezone'))
        await admin.dispose()
        await dispose_engine()
