"""Only finalized, correctly aligned candles can wake a strategy decision."""

import datetime as dt

import pytest
from app.bot.ingest import entry_is_timely, finalized_kline
from app.bot.protection import ProtectionService


@pytest.mark.parametrize(
    "age,allowed", [(-1, False), (0, True), (60, True), (61, False), (14400, False)]
)
def test_entry_window_is_bounded(age: int, allowed: bool) -> None:
    opened = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    assert entry_is_timely(opened, now=opened + dt.timedelta(hours=4, seconds=age)) is allowed


def test_closed_stream_validates_finalization_market_and_alignment() -> None:
    start = int(dt.datetime(2026, 1, 1, tzinfo=dt.UTC).timestamp() * 1000)
    data = {
        "t": start,
        "T": start + 14400000 - 1,
        "s": "BTCUSDT",
        "i": "4h",
        "x": True,
        "o": "60000",
        "h": "60100",
        "l": "59900",
        "c": "60050",
        "v": "10",
    }
    assert finalized_kline({"k": data}, "BTCUSDT", "4h") is not None
    for changed in [{"x": False}, {"s": "ETHUSDT"}, {"i": "1h"}, {"T": start + 1000}]:
        assert finalized_kline({"k": {**data, **changed}}, "BTCUSDT", "4h") is None


def test_user_events_only_wake_account_recovery() -> None:
    service = ProtectionService()
    assert not service.observe({"e": "kline", "E": 1})
    assert service.observe({"e": "ORDER_TRADE_UPDATE", "E": 2})
    assert service.observe({"e": "ALGO_UPDATE", "E": 1})  # reordered events still reconcile truth
