"""Trend Rider v6 strategy plugin: validated v5.2 long engine + vol-sized short
sleeve. Pure and deterministic (BSD §7, Appendix A). Parameters are pinned to the
validated set (the parity gate enforces the engine that backs them).

on_candle emits intents for the just-closed candle; the execution engine sizes and
places orders (Stage 4/5). The full-history engine (engine.py) is the parity anchor.
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd

from app.strategies import engine
from app.strategies.base import (
    Candle,
    EnterLong,
    EnterShort,
    ExitAll,
    Intent,
    MoveStop,
    ResizeShort,
    Strategy,
    StrategyWatch,
    TradeState,
    WatchRule,
    register,
)
from app.strategies.manifest import (
    MarketSpec,
    RiskSpec,
    StrategyEducation,
    StrategyManifest,
    ValidationEvidence,
)


class TrendRiderV6:
    """LONG + SHORT composite using the validated release."""

    manifest = StrategyManifest(
        contract_version=2,
        strategy_id="trend_rider_v6_4h",
        display_name="Trend Rider v6 · 4h",
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

    def __init__(self) -> None:
        self.params: dict[str, float] = {
            "stop_atr": engine.STOP_ATR,
            "tp1_r": engine.TP1_R,
            "tp1_frac": engine.TP1_FRAC,
            "trail_atr": engine.TRAIL_ATR,
            "long_month_cap": engine.LONG_MONTH_CAP,
            "sleeve_depth_atr": engine.SLEEVE_DEPTH_ATR,
            "sleeve_vol_target": engine.SLEEVE_VOL_TARGET,
            "sleeve_weight": engine.SLEEVE_WEIGHT,
            "sleeve_month_cap": engine.SLEEVE_MONTH_CAP,
        }

    def on_candle(self, candles: list[Candle], state: TradeState) -> list[Intent]:
        """Decide intents for the just-closed candle (candles[-1])."""
        if len(candles) < self.manifest.market.warmup_bars:
            return []
        df = _to_frame(candles)
        df = engine.add_indicators(df)
        cur = df.iloc[-1]
        prev = df.iloc[-2]
        atr = float(cur["atr"])
        close = float(cur["close"])
        sma200 = float(cur["sma200"])
        regime = bool(cur["regime"])
        deep_bear = (
            (close < sma200)
            and (float(cur["ema50"]) < float(cur["ema200"]))
            and (close < sma200 - engine.SLEEVE_DEPTH_ATR * atr)
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
                    highest - engine.TRAIL_ATR * atr,
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
            resume = _was_below_then_back(df, state.last_long_closed_at_ms)
            if fresh or resume:
                # The just-closed signal candle is ``cur``; execution occurs at
                # the next bar open, matching engine.long_equity's ``prev`` row.
                stop_dist = engine.STOP_ATR * atr
                intents.append(
                    EnterLong(
                        stop_distance=stop_dist,
                        tp_levels=((engine.TP1_R, engine.TP1_FRAC),),
                        reason="fresh regime" if fresh else "pullback resume",
                    )
                )
        elif deep_bear and not state.halted_short:
            intents.append(
                EnterShort(
                    weight=self._sleeve_weight(df),
                    vol_target=engine.SLEEVE_VOL_TARGET,
                    reason="deep bear",
                )
            )
        return intents

    def inspect(self, candles: list[Candle]) -> StrategyWatch | None:
        """Explain this release's latest state without producing an intent."""
        if len(candles) < self.manifest.market.warmup_bars:
            return None

        frame = engine.add_indicators(_to_frame(candles))
        current = frame.iloc[-1]
        close = float(current["close"])
        ema20 = float(current["ema20"])
        ema50 = float(current["ema50"])
        ema200 = float(current["ema200"])
        sma200 = float(current["sma200"])
        atr = float(current["atr"])
        long_regime = bool(current["regime"])
        deep_bear_threshold = sma200 - engine.SLEEVE_DEPTH_ATR * atr
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
                condition="Close > SMA200 and EMA50 > EMA200",
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
                    "EMA20 after a bull-regime pullback"
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
                    condition=("Close < SMA200, EMA50 < EMA200, and close < SMA200 - 0.5 ATR"),
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
        ret = df["close"].pct_change().fillna(0.0)
        vol_series = ret.ewm(span=engine.SLEEVE_VOL_SPAN, adjust=False).std() * np.sqrt(
            engine.BARS_PER_YEAR
        )
        rv = float(vol_series.iloc[-1])
        if not np.isfinite(rv) or rv <= 0:
            return 0.0
        scale = min(1.0, engine.SLEEVE_VOL_TARGET / rv)
        return engine.SLEEVE_WEIGHT * scale


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


def _was_below_then_back(df: pd.DataFrame, last_long_closed_at_ms: int | None) -> bool:
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
            and int(df.iloc[i]["dt"].timestamp() * 1000) + 4 * 60 * 60 * 1000
            <= last_long_closed_at_ms
        ):
            break
        if bool(below.iloc[i]):
            return True
    return False


PLUGIN: Strategy = register(TrendRiderV6())
