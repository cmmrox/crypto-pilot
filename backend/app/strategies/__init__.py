"""Strategy plugins. Importing this package registers the built-in strategies."""

from __future__ import annotations

from app.strategies import trend_rider_v6, trend_rider_v52  # noqa: F401  (registers)
from app.strategies.base import (
    Candle,
    EnterLong,
    EnterShort,
    ExitAll,
    Halt,
    Intent,
    MoveStop,
    ResizeShort,
    Strategy,
    TakePartial,
    TradeState,
    get_strategy,
    registered_names,
)

__all__ = [
    "Candle",
    "EnterLong",
    "EnterShort",
    "ExitAll",
    "Halt",
    "Intent",
    "MoveStop",
    "ResizeShort",
    "Strategy",
    "TakePartial",
    "TradeState",
    "get_strategy",
    "registered_names",
]
