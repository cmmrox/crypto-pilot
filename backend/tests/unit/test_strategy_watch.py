"""Read-only dashboard explainability tests for Trend Rider v6."""

from __future__ import annotations

from app.strategies.base import Candle
from app.strategies.watch import inspect_strategy_watch


def _candles(closes: list[float]) -> list[Candle]:
    return [
        Candle(
            open_time_ms=index * 14_400_000,
            open=close - 1,
            high=close + 10,
            low=close - 10,
            close=close,
            volume=100,
        )
        for index, close in enumerate(closes)
    ]


def test_watch_requires_full_indicator_warmup() -> None:
    assert inspect_strategy_watch(_candles([50_000 + index for index in range(199)])) is None


def test_watch_exposes_long_regime_thresholds_without_emitting_an_intent() -> None:
    snapshot = inspect_strategy_watch(_candles([50_000 + index * 20 for index in range(240)]))

    assert snapshot is not None
    assert snapshot.long_regime
    assert snapshot.close > snapshot.sma200
    assert snapshot.ema50 > snapshot.ema200
    assert snapshot.deep_bear_threshold == snapshot.sma200 - 0.5 * snapshot.atr14


def test_watch_exposes_deep_bear_condition_for_owner_visibility() -> None:
    closes = [70_000 + index * 15 for index in range(210)]
    closes.extend([73_000 - index * 550 for index in range(30)])
    snapshot = inspect_strategy_watch(_candles(closes))

    assert snapshot is not None
    assert snapshot.close < snapshot.sma200
    assert snapshot.ema50 < snapshot.ema200
    assert snapshot.close < snapshot.deep_bear_threshold
    assert snapshot.deep_bear
