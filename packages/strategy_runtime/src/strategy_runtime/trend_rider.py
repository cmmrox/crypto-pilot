"""Trend Rider v6 strategy plugin: validated v5.2 long engine + vol-sized short
sleeve. Pure and deterministic (BSD §7, Appendix A). Parameters are pinned to the
validated set (the parity gate enforces the engine that backs them).

on_candle emits intents for the just-closed candle; the execution engine sizes and
places orders (Stage 4/5). The full-history engine (engine.py) is the parity anchor.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import numpy as np
import pandas as pd

from strategy_runtime.contracts import (
    Candle,
    EnterLong,
    EnterShort,
    ExitAll,
    Intent,
    MoveStop,
    ResizeShort,
    StrategyWatch,
    TradeState,
    WatchRule,
)
from strategy_runtime.indicators import add_indicators
from strategy_runtime.manifest import (
    MarketSpec,
    RiskSpec,
    StrategyEducation,
    StrategyManifest,
    ValidationEvidence,
)
from strategy_runtime.parameters import INTERVAL_MINUTES, TrendRiderParameters


class TrendRider:
    """LONG + SHORT composite using the validated release."""

    manifest = StrategyManifest(
        contract_version=2,
        strategy_id="trend_rider_v6_4h",
        display_name="Atlas 6 · 4h",
        release="6.0",
        packaged_default=True,
        direction="LONG + SHORT",
        capabilities=(
            "long",
            "short",
            "partial_profit",
            "trailing_stop",
            "independent_monthly_breakers",
            "volatility_targeting",
        ),
        market=MarketSpec(
            symbol="BTCUSDT",
            interval="4h",
            decision_point="closed_candle",
            warmup_bars=200,
            history_bars=3 * 2190 + 200,
        ),
        risk=RiskSpec(
            long_risk_pct=Decimal("15"),
            leverage_cap=Decimal("6"),
            long_monthly_loss_cap=Decimal("0.04"),
            short_monthly_loss_cap=Decimal("0.04"),
            short_resize_drift=Decimal("0.20"),
        ),
        education=StrategyEducation(
            summary="Validated 4h trend strategy with a managed long and short sleeve.",
            description=(
                "Trades BTCUSDT only after a four-hour candle closes. The long engine "
                "follows bullish regimes; the volatility-sized short sleeve participates "
                "in deep bear regimes."
            ),
            entries=(
                "Long on a fresh bull regime or an EMA20 pullback resumption.",
                "Short when price and moving averages confirm a deep-bear regime.",
            ),
            exits=(
                "Longs use TP1, breakeven, a highest-high ATR trail, and regime exit.",
                "Shorts cover when the deep-bear condition ends.",
            ),
            risk_controls=(
                "Long size is stop-distance based and capped at six times leverage.",
                "Long and short books have independent four-percent monthly breakers.",
                "Short size contracts as realized volatility rises.",
            ),
            caveats=(
                "The short sleeve deliberately has no price stop.",
                "Historical results are not a forecast or guarantee.",
            ),
        ),
        validation=ValidationEvidence(
            method="bar-by-bar parity and chronological runtime replay",
            status="verified",
            reference="docs/qa/reports/TREND-RIDER-RUNTIME-PARITY-2026-07-29.md",
        ),
        legacy_ids=("trend_rider_v6",),
    )

    def __init__(
        self,
        parameters: TrendRiderParameters = TrendRiderParameters(),
        interval: str = "4h",
    ) -> None:
        if interval not in INTERVAL_MINUTES:
            raise ValueError("Unsupported timeframe")
        self.parameters = parameters
        self.interval_ms = INTERVAL_MINUTES[interval] * 60_000
        self.bars_per_year = 365 * 24 * 60 // INTERVAL_MINUTES[interval]
        self.params = parameters.values()
        self.manifest = replace(
            self.manifest,
            market=replace(
                self.manifest.market,
                interval=interval,
                warmup_bars=max(200, parameters.slow_period, parameters.sleeve_vol_span),
            ),
            risk=replace(
                self.manifest.risk,
                long_risk_pct=Decimal(str(parameters.risk_pct)),
                leverage_cap=Decimal(str(parameters.leverage_cap)),
                long_monthly_loss_cap=Decimal(str(parameters.long_month_cap)),
                short_monthly_loss_cap=Decimal(str(parameters.sleeve_month_cap)),
            ),
        )

    def on_candle(self, candles: list[Candle], state: TradeState) -> list[Intent]:
        """Decide intents for the just-closed candle (candles[-1])."""
        if len(candles) < self.manifest.market.warmup_bars:
            return []
        df = _to_frame(candles)
        df = add_indicators(df, self.parameters)
        return self.on_prepared_frame(df, state)

    def on_prepared_frame(self, df: pd.DataFrame, state: TradeState) -> list[Intent]:
        """Evaluate only the supplied closed prefix; caller owns indicator preparation.

        Replay can reuse causal indicators instead of rebuilding the entire history
        for every bar. The production on_candle entry point delegates here too.
        """
        if len(df) < self.manifest.market.warmup_bars:
            return []
        cur = df.iloc[-1]
        prev = df.iloc[-2]
        atr = float(cur["atr"])
        close = float(cur["close"])
        sma200 = float(cur["sma200"])
        regime = bool(cur["regime"])
        deep_bear = (
            (close < sma200)
            and (float(cur["ema50"]) < float(cur["ema200"]))
            and (close < sma200 - self.parameters.sleeve_depth_atr * atr)
        )

        intents: list[Intent] = []

        # --- manage / exit an open long ---
        if state.long_position:
            if not regime:
                intents.append(ExitAll(reason="regime off"))
            elif state.tp1_done and state.long_stop is not None:
                highest = (
                    state.highest_high if state.highest_high is not None else float(cur["high"])
                )
                breakeven = state.long_entry if state.long_entry is not None else state.long_stop
                new_stop = max(
                    state.long_stop,
                    breakeven,
                    highest - self.parameters.trail_atr * atr,
                )
                if new_stop > state.long_stop:
                    intents.append(MoveStop(price=new_stop))
            return intents

        # --- manage / cover an open short ---
        if state.short_weight > 0:
            if not deep_bear:
                intents.append(ExitAll(reason="deep-bear ended"))
            else:
                target = self._sleeve_weight(df)
                # The execution engine applies the >20% drift guard using the
                # next-open mark and exchange-rounded quantities.
                intents.append(ResizeShort(target_weight=target))
            return intents

        # --- flat: look for entries ---
        if regime and not state.halted_long:
            fresh = not bool(prev["regime"])
            resume = _was_below_then_back(df, state.last_long_closed_at_ms, self.interval_ms)
            if fresh or resume:
                # The just-closed signal candle is ``cur``; execution occurs at
                # the next bar open, matching engine.long_equity's ``prev`` row.
                stop_dist = self.parameters.stop_atr * atr
                intents.append(
                    EnterLong(
                        stop_distance=stop_dist,
                        tp_levels=((self.parameters.tp1_r, self.parameters.tp1_frac),),
                        reason="fresh regime" if fresh else "pullback resume",
                    )
                )
        elif deep_bear and not state.halted_short:
            intents.append(
                EnterShort(
                    weight=self._sleeve_weight(df),
                    vol_target=self.parameters.sleeve_vol_target,
                    reason="deep bear",
                )
            )
        return intents

    def inspect(self, candles: list[Candle]) -> StrategyWatch | None:
        """Explain this release's latest state without producing an intent."""
        if len(candles) < self.manifest.market.warmup_bars:
            return None

        frame = add_indicators(_to_frame(candles), self.parameters)
        current = frame.iloc[-1]
        close = float(current["close"])
        ema20 = float(current["ema20"])
        ema50 = float(current["ema50"])
        ema200 = float(current["ema200"])
        sma200 = float(current["sma200"])
        atr = float(current["atr"])
        long_regime = bool(current["regime"])
        deep_bear_threshold = sma200 - self.parameters.sleeve_depth_atr * atr
        deep_bear = close < sma200 and ema50 < ema200 and close < deep_bear_threshold
        pullback_resume = _was_below_then_back(frame, None)
        pullback_status = (
            "Ready at last close" if pullback_resume else "Monitoring" if long_regime else "Waiting"
        )
        rules = [
            WatchRule(
                key="long_regime",
                label="Long regime",
                status="Active" if long_regime else "Waiting",
                tone="ok" if long_regime else "neutral",
                active=long_regime,
                condition=(
                    f"Close > SMA{self.parameters.slow_period} and "
                    f"EMA{self.parameters.medium_period} > EMA{self.parameters.slow_period}"
                ),
                threshold=sma200,
            ),
            WatchRule(
                key="pullback_resume",
                label="Pullback resume",
                status=pullback_status,
                tone="ok" if pullback_resume else "warn",
                active=pullback_resume,
                condition=(
                    f"A closed {self.manifest.market.interval} candle reclaims "
                    f"EMA{self.parameters.fast_period} after a bull-regime pullback"
                ),
                threshold=ema20,
            ),
        ]
        if "short" in self.manifest.capabilities:
            rules.append(
                WatchRule(
                    key="deep_bear_short",
                    label="Deep-bear short",
                    status="Active" if deep_bear else "Not active",
                    tone="err" if deep_bear else "neutral",
                    active=deep_bear,
                    condition=(
                        f"Close < SMA{self.parameters.slow_period}, "
                        f"EMA{self.parameters.medium_period} < EMA{self.parameters.slow_period}, "
                        f"and close < SMA{self.parameters.slow_period} - "
                        f"{self.parameters.sleeve_depth_atr:g} ATR"
                    ),
                    threshold=deep_bear_threshold,
                )
            )
        return StrategyWatch(
            last_closed_open_time_ms=candles[-1].open_time_ms,
            rules=tuple(rules),
            disclaimer=(
                f"Thresholds are evaluated on a closed "
                f"{self.manifest.market.interval} candle; they are not a "
                "guaranteed trade or execution price."
            ),
        )

    def _sleeve_weight(self, df: pd.DataFrame) -> float:
        """Current vol-scaled sleeve weight = SLEEVE_WEIGHT * min(1, volT/realized)."""
        if "sleeve_realized_vol" in df:
            rv = float(df["sleeve_realized_vol"].iloc[-1])
            if not np.isfinite(rv) or rv <= 0:
                return 0.0
            return self.parameters.sleeve_weight * min(1.0, self.parameters.sleeve_vol_target / rv)
        ret = df["close"].pct_change().fillna(0.0)
        vol_series = ret.ewm(span=self.parameters.sleeve_vol_span, adjust=False).std() * np.sqrt(
            self.bars_per_year
        )
        rv = float(vol_series.iloc[-1])
        if not np.isfinite(rv) or rv <= 0:
            return 0.0
        scale = min(1.0, self.parameters.sleeve_vol_target / rv)
        return self.parameters.sleeve_weight * scale


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


def _was_below_then_back(
    df: pd.DataFrame, last_long_closed_at_ms: int | None, interval_ms: int = 14_400_000
) -> bool:
    """Pullback-resumption: price dipped below EMA20 recently and the just-closed
    candle is back above it (matches the engine's was_below state)."""
    cur = df.iloc[-1]
    if not (float(cur["close"]) > float(cur["ema20"])):
        return False
    # Look back within the current regime run, but never reuse a pullback that
    # happened while the previous long was open. The validated engine resets
    # this memory while long and starts arming it again on the exit candle.
    below = df["close"] < df["ema20"]
    regime = df["regime"].to_numpy()
    for i in range(len(df) - 2, 0, -1):
        if not regime[i]:
            break
        if (
            last_long_closed_at_ms is not None
            and int(df.iloc[i]["dt"].timestamp() * 1000) + interval_ms <= last_long_closed_at_ms
        ):
            break
        if bool(below.iloc[i]):
            return True
    return False
