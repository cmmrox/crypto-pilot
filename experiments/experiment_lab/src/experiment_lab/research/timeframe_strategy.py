"""Pure higher-timeframe entry confirmation; no change to production v6."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
from strategy_runtime.contracts import EnterLong, EnterShort, Intent, TradeState
from strategy_runtime.indicators import add_indicators
from strategy_runtime.manifest import ValidationEvidence
from strategy_runtime.parameters import INTERVAL_MINUTES, TrendRiderParameters
from strategy_runtime.trend_rider import TrendRider


def align_completed_regime(
    lower: pd.DataFrame, higher: pd.DataFrame, interval: str
) -> pd.DataFrame:
    """Join only 4h information available at the lower candle's CLOSE, never its open.

    Higher bars arrive with open timestamps. Their indicators are unavailable until
    four hours later. A backwards as-of join also handles exact 4h close boundaries.
    """
    high = higher.copy()
    high["dt"] = pd.to_datetime(high["dt"], utc=True)
    if high["dt"].duplicated().any() or not high["dt"].is_monotonic_increasing:
        raise ValueError("Higher timeframe must be ordered and unique")
    for column in ("open", "high", "low", "close", "volume"):
        high[column] = pd.to_numeric(high[column], errors="raise")
    high = add_indicators(high)
    high["htf_long_allowed"] = high["regime"].fillna(False)
    high["htf_short_allowed"] = (high["close"] < high["sma200"]) & (
        high["ema50"] < high["ema200"]
    )
    high["known_at"] = high["dt"] + pd.Timedelta(hours=4)
    low = lower.copy()
    low["decision_at"] = pd.to_datetime(low["dt"], utc=True) + pd.Timedelta(
        minutes=INTERVAL_MINUTES[interval]
    )
    result = pd.merge_asof(
        low,
        high[["known_at", "htf_long_allowed", "htf_short_allowed"]],
        left_on="decision_at",
        right_on="known_at",
        direction="backward",
        tolerance=pd.Timedelta(hours=4),
    )
    # Missing warmup is fail-closed, not a synthetic bullish/bearish regime.
    for column in ("htf_long_allowed", "htf_short_allowed"):
        result[column] = result[column].eq(True)
    return result


class AlignedTrendRider(TrendRider):
    """Retain v6 exits and stop-free short sizing; require 4h alignment for entries.

    This experimental prepared-frame interface requires an externally supplied,
    causal 4h projection. It is deliberately not registered as a deployable plugin.
    """

    def __init__(self, parameters: TrendRiderParameters, interval: str):
        super().__init__(parameters, interval)
        self.manifest = replace(
            self.manifest,
            strategy_id=f"aligned_trend_research_{interval}",
            display_name=f"Research aligned trend {interval}",
            release="research-1",
            packaged_default=False,
            legacy_ids=(),
            validation=ValidationEvidence(
                "retrospective research", "unverified", "offline only"
            ),
        )

    def on_prepared_frame(self, df: pd.DataFrame, state: TradeState) -> list[Intent]:
        intents = super().on_prepared_frame(df, state)
        current = df.iloc[-1]
        return [
            intent
            for intent in intents
            if not (
                isinstance(intent, EnterLong)
                and not bool(current.get("htf_long_allowed", False))
            )
            and not (
                isinstance(intent, EnterShort)
                and not bool(current.get("htf_short_allowed", False))
            )
        ]
