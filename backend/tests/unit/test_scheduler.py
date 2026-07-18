"""Unit tests for 4h candle scheduling math (QA-2)."""

from __future__ import annotations

import datetime as dt

from app.bot.scheduler import (
    DeadMan,
    last_closed_open_time,
    next_close_time,
    seconds_until_next_close,
)


def _utc(y: int, mo: int, d: int, h: int, mi: int = 0, s: int = 0) -> dt.datetime:
    return dt.datetime(y, mo, d, h, mi, s, tzinfo=dt.UTC)


def test_next_close_from_mid_candle() -> None:
    # 13:37 UTC → next 4h close is 16:00.
    assert next_close_time(_utc(2026, 7, 18, 13, 37)) == _utc(2026, 7, 18, 16, 0)


def test_next_close_strictly_after_boundary() -> None:
    # Exactly on a boundary → the *next* one, not the same instant.
    assert next_close_time(_utc(2026, 7, 18, 16, 0)) == _utc(2026, 7, 18, 20, 0)


def test_next_close_wraps_midnight() -> None:
    assert next_close_time(_utc(2026, 7, 18, 21, 5)) == _utc(2026, 7, 19, 0, 0)


def test_last_closed_open_time_mid_candle() -> None:
    # At 13:37, forming candle opened 12:00; last closed opened 08:00.
    assert last_closed_open_time(_utc(2026, 7, 18, 13, 37)) == _utc(2026, 7, 18, 8, 0)


def test_seconds_until_next_close() -> None:
    assert seconds_until_next_close(_utc(2026, 7, 18, 15, 0)) == 3600.0


def test_dead_man_not_overdue_within_window() -> None:
    dm = DeadMan("4h", grace_seconds=900)
    dm.beat(_utc(2026, 7, 18, 16, 0))
    # 4h1m later — within interval+grace.
    assert not dm.is_overdue(_utc(2026, 7, 18, 20, 1))


def test_dead_man_overdue_past_grace() -> None:
    dm = DeadMan("4h", grace_seconds=900)
    dm.beat(_utc(2026, 7, 18, 16, 0))
    # 4h20m later — past interval + 15m grace.
    assert dm.is_overdue(_utc(2026, 7, 18, 20, 20))


def test_dead_man_no_beat_is_not_overdue() -> None:
    assert not DeadMan("4h").is_overdue(_utc(2026, 7, 18, 16, 0))
