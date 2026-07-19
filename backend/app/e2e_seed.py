"""Seed deterministic browser-test fixtures into an isolated test database.

This module is deliberately unavailable outside the explicit E2E configuration.
It makes the historical Stage 2, 6, and 7 Playwright prerequisites reproducible
without copying credentials or production data into CI.

Run inside the test backend container after migrations and owner provisioning:

    python -m app.e2e_seed
"""

from __future__ import annotations

import asyncio
import datetime as dt
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.db.models import Candle, Event, Order, Trade
from app.db.session import dispose_engine, get_sessionmaker
from app.services.notify_config import save_notify_config

_LONG_TRADE_ID = -6001
_SHORT_TRADE_ID = -6002


def _require_isolated_test_mode() -> None:
    settings = get_settings()
    if settings.environment != "test" or not settings.otp_test_mode:
        raise RuntimeError(
            "E2E fixture seeding requires CP_ENVIRONMENT=test and CP_OTP_TEST_MODE=true"
        )
    database_name = str(settings.database_url).rsplit("/", maxsplit=1)[-1].split("?", 1)[0]
    if not database_name.endswith(("_test", "_e2e")):
        raise RuntimeError("E2E fixture database name must end in _test or _e2e")


def _closed_candle_rows() -> list[dict[str, object]]:
    now = dt.datetime.now(dt.UTC)
    current_boundary = now.replace(
        hour=(now.hour // 4) * 4,
        minute=0,
        second=0,
        microsecond=0,
    )
    latest = current_boundary - dt.timedelta(hours=4)
    first = latest - dt.timedelta(hours=4 * 119)
    rows: list[dict[str, object]] = []
    for offset in range(120):
        open_time = first + dt.timedelta(hours=4 * offset)
        price = Decimal("50000.00000000") + Decimal(offset)
        rows.append(
            {
                "symbol": "BTCUSDT",
                "interval": "4h",
                "open_time": open_time,
                "open": price,
                "high": price + Decimal("100.00000000"),
                "low": price - Decimal("100.00000000"),
                "close": price + Decimal("25.00000000"),
                "volume": Decimal("10.00000000"),
                "closed": True,
            }
        )
    return rows


async def seed() -> None:
    _require_isolated_test_mode()
    async with get_sessionmaker()() as session:
        candle_stmt = (
            insert(Candle)
            .values(_closed_candle_rows())
            .on_conflict_do_nothing(
                index_elements=[Candle.symbol, Candle.interval, Candle.open_time]
            )
        )
        await session.execute(candle_stmt)

        trade_rows = [
            {
                "id": _LONG_TRADE_ID,
                "opened_at": dt.datetime(2026, 7, 2, 0, tzinfo=dt.UTC),
                "closed_at": dt.datetime(2026, 7, 3, 0, tzinfo=dt.UTC),
                "side": "LONG",
                "entry_px": Decimal("50000.00000000"),
                "exit_px": Decimal("52000.00000000"),
                "qty": Decimal("0.10000000"),
                "fees": Decimal("5.00000000"),
                "funding": Decimal("0.00000000"),
                "realized_pnl": Decimal("200.00000000"),
                "r_multiple": Decimal("2.00000000"),
                "exit_reason": "4 ATR trail",
                "strategy": "trend_rider_v6",
                "environment": "DEMO",
            },
            {
                "id": _SHORT_TRADE_ID,
                "opened_at": dt.datetime(2026, 7, 10, 0, tzinfo=dt.UTC),
                "closed_at": dt.datetime(2026, 7, 11, 0, tzinfo=dt.UTC),
                "side": "SHORT",
                "entry_px": Decimal("51000.00000000"),
                "exit_px": Decimal("51500.00000000"),
                "qty": Decimal("0.10000000"),
                "fees": Decimal("4.00000000"),
                "funding": Decimal("0.00000000"),
                "realized_pnl": Decimal("-50.00000000"),
                "r_multiple": Decimal("-0.50000000"),
                "exit_reason": "bear regime ended",
                "strategy": "trend_rider_v6",
                "environment": "DEMO",
            },
        ]
        trade_stmt = insert(Trade).values(trade_rows)
        await session.execute(
            trade_stmt.on_conflict_do_update(
                index_elements=[Trade.id],
                set_={
                    column: getattr(trade_stmt.excluded, column)
                    for column in (
                        "opened_at",
                        "closed_at",
                        "side",
                        "entry_px",
                        "exit_px",
                        "qty",
                        "fees",
                        "funding",
                        "realized_pnl",
                        "r_multiple",
                        "exit_reason",
                        "strategy",
                        "environment",
                    )
                },
            )
        )

        order_rows = [
            {
                "id": -6101,
                "binance_order_id": "e2e-long-entry",
                "client_order_id": "e2e-seed-long-entry",
                "trade_id": _LONG_TRADE_ID,
                "type": "MARKET",
                "status": "FILLED",
                "price": Decimal("50000.00000000"),
                "stop_price": None,
                "qty": Decimal("0.10000000"),
                "reduce_only": False,
                "placed_at": dt.datetime(2026, 7, 2, 0, tzinfo=dt.UTC),
                "filled_at": dt.datetime(2026, 7, 2, 0, tzinfo=dt.UTC),
                "raw_json": {"fixture": "e2e"},
            },
            {
                "id": -6102,
                "binance_order_id": "e2e-long-stop",
                "client_order_id": "e2e-seed-long-stop",
                "trade_id": _LONG_TRADE_ID,
                "type": "STOP_MARKET",
                "status": "FILLED",
                "price": None,
                "stop_price": Decimal("52000.00000000"),
                "qty": Decimal("0.10000000"),
                "reduce_only": True,
                "placed_at": dt.datetime(2026, 7, 3, 0, tzinfo=dt.UTC),
                "filled_at": dt.datetime(2026, 7, 3, 0, tzinfo=dt.UTC),
                "raw_json": {"fixture": "e2e"},
            },
            {
                "id": -6103,
                "binance_order_id": "e2e-short-entry",
                "client_order_id": "e2e-seed-short-entry",
                "trade_id": _SHORT_TRADE_ID,
                "type": "MARKET",
                "status": "FILLED",
                "price": Decimal("51000.00000000"),
                "stop_price": None,
                "qty": Decimal("0.10000000"),
                "reduce_only": False,
                "placed_at": dt.datetime(2026, 7, 10, 0, tzinfo=dt.UTC),
                "filled_at": dt.datetime(2026, 7, 10, 0, tzinfo=dt.UTC),
                "raw_json": {"fixture": "e2e"},
            },
        ]
        order_stmt = insert(Order).values(order_rows)
        await session.execute(
            order_stmt.on_conflict_do_update(
                index_elements=[Order.id],
                set_={
                    column: getattr(order_stmt.excluded, column)
                    for column in (
                        "binance_order_id",
                        "client_order_id",
                        "trade_id",
                        "type",
                        "status",
                        "price",
                        "stop_price",
                        "qty",
                        "reduce_only",
                        "placed_at",
                        "filled_at",
                        "raw_json",
                    )
                },
            )
        )

        event_stmt = insert(Event).values(
            id=-6201,
            ts=dt.datetime(2026, 7, 1, 0, tzinfo=dt.UTC),
            level="INFO",
            category="system",
            message="Candle ingest (E2E fixture) — 0 gap(s)",
            payload_json={"reason": "e2e_fixture", "gaps": 0, "environment": "DEMO"},
            sms_status=None,
            ref="e2e_seed:candle_ingest",
        )
        await session.execute(
            event_stmt.on_conflict_do_update(
                index_elements=[Event.id],
                set_={
                    "ts": event_stmt.excluded.ts,
                    "level": event_stmt.excluded.level,
                    "category": event_stmt.excluded.category,
                    "message": event_stmt.excluded.message,
                    "payload_json": event_stmt.excluded.payload_json,
                    "sms_status": event_stmt.excluded.sms_status,
                    "ref": event_stmt.excluded.ref,
                },
            )
        )

        await save_notify_config(
            session,
            user_id="e2e-user",
            api_key="e2e-api-key",
            sender_id="NotifyDEMO",
            phone="94711234567",
        )
        await session.commit()


async def _main() -> None:
    try:
        await seed()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
    print("E2E fixtures seeded.")
