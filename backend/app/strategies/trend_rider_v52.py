"""Trend Rider v5.2 strategy plugin: the validated long-only fallback.

Identical long engine to v6 with the short sleeve disabled (BSD: registered
fallback, long-only). Pure and deterministic.
"""

from __future__ import annotations

from app.strategies.base import Candle, Intent, Strategy, TradeState, register
from app.strategies.trend_rider_v6 import TrendRiderV6


class TrendRiderV52(TrendRiderV6):
    """Long-only: same regime/entry/management rules, no short sleeve."""

    name = "trend_rider_v52"
    validated_release = "5.2"

    def on_candle(self, candles: list[Candle], state: TradeState) -> list[Intent]:
        # Never hold or open a short; drop any short intents the base would emit.
        intents = super().on_candle(candles, state)
        return [i for i in intents if type(i).__name__ not in {"EnterShort", "ResizeShort"}]


trend_rider_v52: Strategy = register(TrendRiderV52())
