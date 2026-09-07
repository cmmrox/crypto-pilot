"""Pure closed-4h long/flat hypotheses, separate from the validated v6 plugin."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Literal

import pandas as pd
from strategy_runtime.contracts import EnterLong, ExitAll, MoveStop, TradeState


@dataclass(frozen=True)
class Parameters:
    family: Literal["pullback", "breakout"]
    lookback: int = 20
    entry_atr: float = 0.5
    stop_atr: float = 2.5
    trail_atr: float = 4.0

    def __post_init__(self) -> None:
        if self.family not in {"pullback", "breakout"}:
            raise ValueError("Unknown hypothesis")
        if type(self.lookback) is not int or not 10 <= self.lookback <= 60:
            raise ValueError("Lookback must be between 10 and 60 closed bars")
        for value, low, high in (
            (self.entry_atr, 0, 2),
            (self.stop_atr, 1, 4),
            (self.trail_atr, 1, 6),
        ):
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError("Invalid ATR multiple")


class RegimeLong:
    """Buy a discounted uptrend or confirmed breakout; remain flat in bearish regimes.

    Indicators are causal and may be prepared in bulk. Evaluation receives just one
    CLOSED-bar snapshot. Execution, risk, sizing, fees and funding belong to the adapter.
    No averaging down, shorting, order API or mutable learning state.
    """

    name = "regime_long_research_4h_v1"

    def __init__(self, parameters: Parameters):
        self.parameters = parameters

    def prepare(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        close = result["close"].astype(float)
        slow = close.ewm(span=200, adjust=False).mean()
        result["research_risk_on"] = (close > slow) & (slow > slow.shift(6))
        result["research_center"] = close.ewm(
            span=self.parameters.lookback, adjust=False
        ).mean()
        # Excluding the decision candle prevents a self-referential breakout.
        result["research_channel"] = (
            result["high"].shift(1).rolling(self.parameters.lookback).max()
        )
        return result

    def decide(
        self, closed: pd.Series[Any], state: TradeState
    ) -> list[EnterLong | ExitAll | MoveStop]:
        # Rows mix numeric indicators, a timestamp and a boolean regime flag.
        atr = float(closed["atr"])
        if not math.isfinite(atr) or atr <= 0:
            return []
        close = float(closed["close"])
        risk_on = bool(closed["research_risk_on"])
        center = float(closed["research_center"])
        if state.long_position:
            if not risk_on:
                return [ExitAll("research_regime_off")]
            if self.parameters.family == "pullback" and close >= center:
                return [ExitAll("research_mean_recovered")]
            stop = (state.highest_high or close) - self.parameters.trail_atr * atr
            if state.tp1_done and state.long_entry is not None:
                stop = max(stop, state.long_entry)
            return [MoveStop(stop)]
        if state.halted_long or not risk_on:
            return []
        candle_ms = int(pd.Timestamp(closed["dt"]).timestamp() * 1000)
        if state.last_long_closed_at_ms is not None:
            if candle_ms <= state.last_long_closed_at_ms:
                return []
        entry = (
            close < center - self.parameters.entry_atr * atr
            if self.parameters.family == "pullback"
            else close > float(closed["research_channel"])
        )
        return (
            [
                EnterLong(
                    self.parameters.stop_atr * atr,
                    ((1.0, 0.5),),
                    self.parameters.family,
                )
            ]
            if entry
            else []
        )
