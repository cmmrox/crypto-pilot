"""Scheduling helpers: 4h candle-close alignment (UTC) and dead-man tracking.

Pure time math kept separate from the loop so it is deterministic and unit-testable
(TimeProvider injection). Trading decisions occur only on closed 4h candles.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

# 4h candles close at 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC.
INTERVAL_SECONDS: dict[str, int] = {"4h": 4 * 3600, "1h": 3600, "1d": 24 * 3600}

TimeProvider = Callable[[], dt.datetime]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def last_closed_open_time(now: dt.datetime, interval: str = "4h") -> dt.datetime:
    """Open-time of the most recently *closed* candle at `now`.

    The candle opening at T closes at T+interval. So at `now`, the last fully
    closed candle opened at floor(now, interval) - interval when now is exactly on
    a boundary, otherwise floor(now, interval) - interval.
    """
    step = INTERVAL_SECONDS[interval]
    epoch = int(now.timestamp())
    floored = epoch - (epoch % step)  # open time of the currently-forming candle
    # The currently-forming candle (opened at `floored`) is not yet closed, so the
    # last closed candle opened one step earlier.
    return dt.datetime.fromtimestamp(floored - step, tz=dt.UTC)


def next_close_time(now: dt.datetime, interval: str = "4h") -> dt.datetime:
    """The next UTC instant at which a candle closes (strictly after `now`)."""
    step = INTERVAL_SECONDS[interval]
    epoch = int(now.timestamp())
    next_boundary = epoch - (epoch % step) + step
    return dt.datetime.fromtimestamp(next_boundary, tz=dt.UTC)


def seconds_until_next_close(now: dt.datetime, interval: str = "4h") -> float:
    """Seconds from `now` until the next candle close."""
    return (next_close_time(now, interval) - now).total_seconds()


class DeadMan:
    """Tracks the last heartbeat; flags a missed tick past the interval + grace."""

    def __init__(self, interval: str = "4h", grace_seconds: int = 900) -> None:
        self._interval_s = INTERVAL_SECONDS[interval]
        self._grace = grace_seconds
        self._last_tick: dt.datetime | None = None

    def beat(self, now: dt.datetime) -> None:
        self._last_tick = now

    @property
    def last_tick(self) -> dt.datetime | None:
        return self._last_tick

    def is_overdue(self, now: dt.datetime) -> bool:
        if self._last_tick is None:
            return False
        elapsed = (now - self._last_tick).total_seconds()
        return elapsed > self._interval_s + self._grace
