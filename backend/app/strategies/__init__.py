"""Public strategy contract and automatically discovered plugin catalog."""

from __future__ import annotations

from app.strategies.base import (
    Candle,
    EnterLong,
    EnterShort,
    EnterShortStop,
    ExitAll,
    Halt,
    Intent,
    MoveStop,
    ResizeShort,
    Strategy,
    StrategyWatch,
    TakePartial,
    TradeState,
    WatchRule,
)
from app.strategies.catalog import (
    canonical_strategy_id,
    default_strategy,
    get_strategy,
    registered_names,
    registered_strategies,
)
from app.strategies.manifest import (
    MarketSpec,
    RiskSpec,
    StrategyEducation,
    StrategyManifest,
    ValidationEvidence,
)

__all__ = [
    "Candle",
    "EnterLong",
    "EnterShort",
    "EnterShortStop",
    "ExitAll",
    "Halt",
    "Intent",
    "MarketSpec",
    "MoveStop",
    "ResizeShort",
    "RiskSpec",
    "Strategy",
    "StrategyEducation",
    "StrategyManifest",
    "StrategyWatch",
    "TakePartial",
    "TradeState",
    "ValidationEvidence",
    "WatchRule",
    "canonical_strategy_id",
    "default_strategy",
    "get_strategy",
    "registered_names",
    "registered_strategies",
]
