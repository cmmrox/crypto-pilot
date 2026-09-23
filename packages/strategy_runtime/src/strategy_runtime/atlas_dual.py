"""Atlas 7 Dual: trend-pullback and squeeze-breakout entries on closed 4h candles.

Pure and deterministic (BSD §7): indicators in, abstract intents out. No I/O, no
clocks, no sizing, no orders. Both books carry a protective price stop, so the short
side emits ``EnterShortStop`` rather than the stop-free ``EnterShort`` sleeve used by
Trend Rider v6, which this release does not modify.

Research evidence: docs/qa/reports/MONTHLY-INCOME-STRATEGY-RESEARCH-2026-09-22.md
(engine and parameter search under experiments/monthly_income_research).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

import numpy as np
import pandas as pd

from strategy_runtime.contracts import (
    Candle,
    EnterLong,
    EnterShortStop,
    ExitAll,
    Intent,
    MoveStop,
    StrategyWatch,
    TradeState,
    WatchRule,
)
from strategy_runtime.manifest import (
    MarketSpec,
    RiskSpec,
    StrategyEducation,
    StrategyManifest,
    ValidationEvidence,
)


@dataclass(frozen=True)
class AtlasDualParameters:
    """Pinned release parameters. Research candidates ship as new releases."""

    fast_period: int = 20  # pullback EMA
    medium_period: int = 50  # regime EMA
    slow_period: int = 200  # regime SMA/EMA
    atr_period: int = 14
    hysteresis_atr: float = 1.0  # buffer around the slow SMA
    stop_atr: float = 2.5  # protective stop distance, both sides
    tp1_r: float = 2.0  # first target in R
    tp1_frac: float = 0.4  # fraction closed at the first target
    trail_atr: float = 3.0  # trail from the extreme, after the first target
    range_bars: int = 24  # squeeze range window
    width_lookback: int = 360  # percentile window for the range width
    width_quantile: float = 0.35  # "tight" threshold
    risk_pct: float = 4.0
    leverage_cap: float = 3.0
    monthly_loss_cap: float = 0.08  # per side, about twice the risk per trade

    def values(self) -> dict[str, float]:
        return {key: float(value) for key, value in asdict(self).items()}


def add_indicators(
    df: pd.DataFrame, params: AtlasDualParameters = AtlasDualParameters()
) -> pd.DataFrame:
    """Causal indicators: every value at row k uses rows <= k only."""
    out = df.copy()
    close = out["close"]
    out["sma_slow"] = close.rolling(params.slow_period).mean()
    out["ema_fast"] = close.ewm(span=params.fast_period, adjust=False).mean()
    out["ema_medium"] = close.ewm(span=params.medium_period, adjust=False).mean()
    out["ema_slow"] = close.ewm(span=params.slow_period, adjust=False).mean()
    previous_close = close.shift()
    true_range = np.maximum(
        out["high"] - out["low"],
        np.maximum((out["high"] - previous_close).abs(), (out["low"] - previous_close).abs()),
    )
    out["atr"] = true_range.ewm(alpha=1 / params.atr_period, adjust=False).mean()
    buffer = params.hysteresis_atr * out["atr"]
    out["bull_line"] = out["sma_slow"] + buffer
    out["bear_line"] = out["sma_slow"] - buffer
    out["bull"] = (close > out["bull_line"]) & (out["ema_medium"] > out["ema_slow"])
    out["bear"] = (close < out["bear_line"]) & (out["ema_medium"] < out["ema_slow"])
    # Squeeze: the range of the previous `range_bars` bars, measured before this bar.
    out["range_high"] = out["high"].rolling(params.range_bars).max().shift(1)
    out["range_low"] = out["low"].rolling(params.range_bars).min().shift(1)
    width = (out["range_high"] - out["range_low"]) / close
    threshold = width.rolling(params.width_lookback).quantile(params.width_quantile)
    out["width"] = width
    out["was_tight"] = (width <= threshold).shift(1, fill_value=False).astype(bool)
    return out


def _resumed(
    df: pd.DataFrame, *, bullish: bool, since_ms: int | None = None, interval_ms: int = 14_400_000
) -> bool:
    """True when price closed back on the trend side of the pullback EMA.

    The pullback must have happened inside the current regime run *and* after this
    book last closed a position, so one pullback is traded once: without that
    memory a stopped-out trade would re-enter on the very next candle.
    """
    regime = df["bull"] if bullish else df["bear"]
    if not bool(regime.iloc[-1]):
        return False
    close = df["close"]
    ema_fast = df["ema_fast"]
    back_on_side = (
        close.iloc[-1] > ema_fast.iloc[-1] if bullish else close.iloc[-1] < ema_fast.iloc[-1]
    )
    if not back_on_side:
        return False
    times = df.get("dt")
    for index in range(len(df) - 2, -1, -1):
        if not bool(regime.iloc[index]):
            return False
        if since_ms is not None and times is not None:
            closed_at_ms = int(pd.Timestamp(times.iloc[index]).timestamp() * 1000) + interval_ms
            if closed_at_ms <= since_ms:
                return False
        pulled_back = (
            close.iloc[index] < ema_fast.iloc[index]
            if bullish
            else close.iloc[index] > ema_fast.iloc[index]
        )
        if pulled_back:
            return True
    return False


class AtlasDual:
    """One position at a time, long or short, with a stop on every entry."""

    manifest = StrategyManifest(
        contract_version=2,
        strategy_id="atlas_dual_v1_4h",
        display_name="Atlas 7 Dual · 4h",
        release="1.0",
        packaged_default=False,
        direction="LONG + SHORT",
        capabilities=(
            "long",
            "short",
            "protective_stop_both_sides",
            "partial_profit",
            "trailing_stop",
            "independent_monthly_breakers",
        ),
        market=MarketSpec(
            symbol="BTCUSDT",
            interval="4h",
            decision_point="closed_candle",
            warmup_bars=400,
            history_bars=3 * 2190 + 400,
        ),
        risk=RiskSpec(
            long_risk_pct=Decimal("4"),
            leverage_cap=Decimal("3"),
            long_monthly_loss_cap=Decimal("0.08"),
            short_monthly_loss_cap=Decimal("0.08"),
            short_resize_drift=Decimal("0.20"),
        ),
        education=StrategyEducation(
            summary="Four-hour trend and breakout strategy with a stop on every trade.",
            description=(
                "Trades BTCUSDT only after a four-hour candle closes. It enters either "
                "on a pullback inside an established trend or on a breakout from an "
                "unusually tight range, in the direction of the regime. Longs and shorts "
                "use the same rules, sizing and protective stop."
            ),
            entries=(
                "Pullback: price closes back through the 20 EMA inside the regime.",
                "Breakout: a tight 24-candle range breaks in the regime direction.",
            ),
            exits=(
                "Protective stop 2.5 ATR from entry on both sides.",
                "40% at twice the risk, then a 3 ATR trail from the best price reached.",
                "Regime exit when the close crosses the buffered 200 SMA against the trade.",
            ),
            risk_controls=(
                "Risk 4% of equity per trade, capped at three times leverage.",
                "Independent 8% monthly loss breakers for the long and short books.",
                "A one-ATR buffer around the 200 SMA keeps the regime from flip-flopping.",
            ),
            caveats=(
                "Backtests showed roughly six profitable months in ten, not every month.",
                "The 4% profile drew down about 38% in the research replay.",
                "Historical results are not a forecast or guarantee.",
            ),
        ),
        validation=ValidationEvidence(
            method="unit rules, chronological bot replay, DEMO order lifecycle",
            status="verified",
            reference="docs/qa/reports/ATLAS-7-DUAL-RELEASE-2026-09-22.md",
        ),
    )

    def __init__(self, parameters: AtlasDualParameters = AtlasDualParameters()) -> None:
        self.parameters = parameters
        self.params = parameters.values()

    def on_candle(self, candles: list[Candle], state: TradeState) -> list[Intent]:
        if len(candles) < self.manifest.market.warmup_bars:
            return []
        return self.on_prepared_frame(add_indicators(_to_frame(candles), self.parameters), state)

    def on_prepared_frame(self, df: pd.DataFrame, state: TradeState) -> list[Intent]:
        """Evaluate the supplied closed prefix; the caller owns indicator prep."""
        if len(df) < self.manifest.market.warmup_bars:
            return []
        current = df.iloc[-1]
        atr = float(current["atr"])
        close = float(current["close"])
        if not np.isfinite(atr) or atr <= 0 or not np.isfinite(float(current["sma_slow"])):
            return []
        stop_distance = self.parameters.stop_atr * atr
        tp_levels = ((self.parameters.tp1_r, self.parameters.tp1_frac),)
        bull_line = float(current["bull_line"])
        bear_line = float(current["bear_line"])
        long_signal, long_reason = self._entry(
            df, bullish=True, since_ms=state.last_long_closed_at_ms
        )
        short_signal, short_reason = self._entry(
            df, bullish=False, since_ms=state.last_short_closed_at_ms
        )

        # A qualifying opposite signal reverses in one decision; otherwise the
        # buffered regime line closes the trade. Order matters: the reversal is
        # checked first so a sharp turn is traded rather than only exited.
        if state.long_position:
            if short_signal and not state.halted_short:
                return [
                    ExitAll(reason="reverse to short"),
                    EnterShortStop(
                        stop_distance=stop_distance, tp_levels=tp_levels, reason=short_reason
                    ),
                ]
            if close < bear_line:
                return [ExitAll(reason="regime exit")]
            return self._trail_long(state, atr)

        if state.short_position:
            if long_signal and not state.halted_long:
                return [
                    ExitAll(reason="reverse to long"),
                    EnterLong(stop_distance=stop_distance, tp_levels=tp_levels, reason=long_reason),
                ]
            if close > bull_line:
                return [ExitAll(reason="regime exit")]
            return self._trail_short(state, atr)

        if long_signal and not state.halted_long:
            return [EnterLong(stop_distance=stop_distance, tp_levels=tp_levels, reason=long_reason)]
        if short_signal and not state.halted_short:
            return [
                EnterShortStop(
                    stop_distance=stop_distance, tp_levels=tp_levels, reason=short_reason
                )
            ]
        return []

    def _entry(
        self, df: pd.DataFrame, *, bullish: bool, since_ms: int | None = None
    ) -> tuple[bool, str]:
        """Pullback or breakout entry for one side, with the reason that fired."""
        current = df.iloc[-1]
        previous = df.iloc[-2]
        regime_now = bool(current["bull"] if bullish else current["bear"])
        close = float(current["close"])
        line = float(current["bull_line"] if bullish else current["bear_line"])
        if regime_now:
            fresh = not bool(previous["bull"] if bullish else previous["bear"])
            if fresh:
                return True, "fresh regime"
            if _resumed(df, bullish=bullish, since_ms=since_ms):
                return True, "pullback resume"
        if bool(current["was_tight"]):
            level = float(current["range_high"] if bullish else current["range_low"])
            if np.isfinite(level):
                broke = close > level if bullish else close < level
                beyond_line = close > line if bullish else close < line
                if broke and beyond_line:
                    return True, "squeeze breakout"
        return False, ""

    def _trail_long(self, state: TradeState, atr: float) -> list[Intent]:
        if not state.tp1_done or state.long_stop is None:
            return []
        extreme = state.highest_high if state.highest_high is not None else state.long_entry
        if extreme is None:
            return []
        breakeven = state.long_entry if state.long_entry is not None else state.long_stop
        new_stop = max(state.long_stop, breakeven, extreme - self.parameters.trail_atr * atr)
        return [MoveStop(price=new_stop)] if new_stop > state.long_stop else []

    def _trail_short(self, state: TradeState, atr: float) -> list[Intent]:
        if not state.tp1_done or state.short_stop is None:
            return []
        extreme = state.lowest_low if state.lowest_low is not None else state.short_entry
        if extreme is None:
            return []
        breakeven = state.short_entry if state.short_entry is not None else state.short_stop
        new_stop = min(state.short_stop, breakeven, extreme + self.parameters.trail_atr * atr)
        return [MoveStop(price=new_stop)] if new_stop < state.short_stop else []

    def inspect(self, candles: list[Candle]) -> StrategyWatch | None:
        """Read-only projection of this release's conditions for the owner console."""
        if len(candles) < self.manifest.market.warmup_bars:
            return None
        df = add_indicators(_to_frame(candles), self.parameters)
        current = df.iloc[-1]
        close = float(current["close"])
        bull = bool(current["bull"])
        bear = bool(current["bear"])
        tight = bool(current["was_tight"])
        long_ready, long_reason = self._entry(df, bullish=True)
        short_ready, short_reason = self._entry(df, bullish=False)
        rules = (
            WatchRule(
                key="regime",
                label="Regime",
                status="Bull" if bull else "Bear" if bear else "Neutral",
                tone="ok" if bull else "err" if bear else "neutral",
                active=bull or bear,
                condition=(
                    f"Close beyond SMA{self.parameters.slow_period} by "
                    f"{self.parameters.hysteresis_atr:g} ATR with "
                    f"EMA{self.parameters.medium_period} on the same side"
                ),
                threshold=float(current["bull_line"]) if not bear else float(current["bear_line"]),
            ),
            WatchRule(
                key="pullback",
                label="Pullback entry",
                status="Ready at last close" if long_ready or short_ready else "Monitoring",
                tone="ok" if long_ready or short_ready else "neutral",
                active=long_ready or short_ready,
                condition=(
                    f"Close returns through EMA{self.parameters.fast_period} inside the regime"
                ),
                threshold=float(current["ema_fast"]),
            ),
            WatchRule(
                key="squeeze",
                label="Squeeze breakout",
                status=(
                    "Range tight" if tight and not (long_ready or short_ready) else "Not armed"
                ),
                tone="warn" if tight else "neutral",
                active=tight,
                condition=(
                    f"Previous {self.parameters.range_bars}-candle range in the tightest "
                    f"{self.parameters.width_quantile:.0%} of {self.parameters.width_lookback} "
                    "bars, then broken in the regime direction"
                ),
                threshold=float(current["range_high"]) if close >= 0 else None,
            ),
        )
        reason = long_reason or short_reason
        return StrategyWatch(
            last_closed_open_time_ms=candles[-1].open_time_ms,
            rules=rules,
            disclaimer=(
                "Thresholds are evaluated on a closed 4h candle"
                + (f" (latest signal: {reason})" if reason else "")
                + "; they are not a guaranteed trade or execution price."
            ),
        )


def _to_frame(candles: list[Candle]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "dt": pd.to_datetime([c.open_time_ms for c in candles], unit="ms", utc=True),
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
        }
    )
