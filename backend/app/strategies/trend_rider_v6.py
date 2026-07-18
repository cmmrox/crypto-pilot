"""Trend Rider v6 strategy plugin: validated v5.2 long engine + vol-sized short
sleeve. Pure and deterministic (BSD §7, Appendix A). Parameters are pinned to the
validated set (the parity gate enforces the engine that backs them).

on_candle emits intents for the just-closed candle; the execution engine sizes and
places orders (Stage 4/5). The full-history engine (engine.py) is the parity anchor.
"""

from __future__ import annotations

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
    TradeState,
    register,
)

RESIZE_DRIFT = 0.20  # resize the short only when the target drifts >20%


class TrendRiderV6:
    """LONG + SHORT composite. name/params match the validated release."""

    name = "trend_rider_v6"
    validated_release = "6.0"

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

    def warmup_bars(self) -> int:
        return 200

    def on_candle(self, candles: list[Candle], state: TradeState) -> list[Intent]:
        """Decide intents for the just-closed candle (candles[-1])."""
        if len(candles) < self.warmup_bars():
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
                trail = close  # engine trails from highest-high; live uses current close proxy
                new_stop = max(state.long_stop, trail - engine.TRAIL_ATR * atr)
                if new_stop > state.long_stop:
                    intents.append(MoveStop(price=new_stop))
            return intents

        # --- manage / cover an open short ---
        if state.short_weight > 0:
            if not deep_bear:
                intents.append(ExitAll(reason="deep-bear ended"))
            else:
                target = self._sleeve_weight(df)
                drift = abs(target - state.short_weight) / state.short_weight
                if drift > RESIZE_DRIFT:
                    intents.append(ResizeShort(target_weight=target))
            return intents

        # --- flat: look for entries ---
        if regime and not state.halted_long:
            fresh = not bool(prev["regime"])
            resume = _was_below_then_back(df)
            if fresh or resume:
                stop_dist = engine.STOP_ATR * float(prev["atr"])
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


def _was_below_then_back(df: pd.DataFrame) -> bool:
    """Pullback-resumption: price dipped below EMA20 recently and the just-closed
    candle is back above it (matches the engine's was_below state)."""
    prev = df.iloc[-2]
    if not (float(prev["close"]) > float(prev["ema20"])):
        return False
    # look back within the current regime run for a close below EMA20
    below = df["close"] < df["ema20"]
    regime = df["regime"].to_numpy()
    for i in range(len(df) - 2, 0, -1):
        if not regime[i]:
            break
        if bool(below.iloc[i]):
            return True
    return False


trend_rider_v6: Strategy = register(TrendRiderV6())
