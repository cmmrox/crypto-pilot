"""Trend Rider v5.2 strategy plugin: the validated long-only fallback.

Identical long engine to v6 with the short sleeve disabled (BSD: registered
fallback, long-only). Pure and deterministic.
"""

from __future__ import annotations

from dataclasses import replace

from app.strategies.base import (
    Candle,
    EnterShort,
    Intent,
    ResizeShort,
    Strategy,
    TradeState,
    register,
)
from app.strategies.manifest import StrategyEducation, ValidationEvidence
from app.strategies.plugins.trend_rider_v6_4h import TrendRiderV6


class TrendRiderV52(TrendRiderV6):
    """Long-only: same regime/entry/management rules, no short sleeve."""

    manifest = replace(
        TrendRiderV6.manifest,
        strategy_id="trend_rider_v52_4h",
        display_name="Trend Rider v5.2 · 4h",
        release="5.2",
        packaged_default=False,
        direction="LONG ONLY",
        capabilities=(
            "long",
            "partial_profit",
            "trailing_stop",
            "monthly_breaker",
        ),
        education=StrategyEducation(
            summary="Validated 4h long-only fallback for bullish BTC regimes.",
            description=(
                "Uses the same Trend Rider long engine as v6 but never opens or "
                "manages a short sleeve."
            ),
            entries=("Long on a fresh bull regime or an EMA20 pullback resumption.",),
            exits=("TP1, breakeven, highest-high ATR trail, and bull-regime exit.",),
            risk_controls=(
                "Stop-distance sizing with a six-times leverage ceiling.",
                "Four-percent monthly long-book breaker.",
            ),
            caveats=(
                "The strategy remains flat during bear regimes.",
                "Historical results are not a forecast or guarantee.",
            ),
        ),
        validation=ValidationEvidence(
            method="bar-by-bar parity",
            status="verified",
            reference="docs/qa/reports/STAGE-03-REPORT.md",
        ),
        legacy_ids=("trend_rider_v52",),
    )

    def on_candle(self, candles: list[Candle], state: TradeState) -> list[Intent]:
        # Never hold or open a short; drop any short intents the base would emit.
        intents = super().on_candle(candles, state)
        return [intent for intent in intents if not isinstance(intent, EnterShort | ResizeShort)]


PLUGIN: Strategy = register(TrendRiderV52())
