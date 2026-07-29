"""Read-only dashboard explainability tests for Trend Rider v6."""

from __future__ import annotations

from app.strategies import get_strategy
from app.strategies.base import Candle


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
    strategy = get_strategy("trend_rider_v6_4h")
    assert strategy.inspect(_candles([50_000 + index for index in range(199)])) is None


def test_watch_exposes_long_regime_thresholds_without_emitting_an_intent() -> None:
    strategy = get_strategy("trend_rider_v6_4h")
    closes = [50_000 + index * 20 for index in range(240)]
    snapshot = strategy.inspect(_candles(closes))

    assert snapshot is not None
    by_key = {rule.key: rule for rule in snapshot.rules}
    assert by_key["long_regime"].active
    assert by_key["long_regime"].threshold is not None
    assert closes[-1] > by_key["long_regime"].threshold
    assert by_key["pullback_resume"].condition.startswith("A closed 4h candle")


def test_watch_exposes_deep_bear_condition_for_owner_visibility() -> None:
    closes = [70_000 + index * 15 for index in range(210)]
    closes.extend([73_000 - index * 550 for index in range(30)])
    strategy = get_strategy("trend_rider_v6_4h")
    snapshot = strategy.inspect(_candles(closes))

    assert snapshot is not None
    rule = next(rule for rule in snapshot.rules if rule.key == "deep_bear_short")
    assert rule.active
    assert rule.threshold is not None
    assert closes[-1] < rule.threshold


def test_long_only_watch_does_not_publish_short_rules() -> None:
    strategy = get_strategy("trend_rider_v52_4h")
    snapshot = strategy.inspect(_candles([50_000 + index * 20 for index in range(240)]))

    assert snapshot is not None
    assert {rule.key for rule in snapshot.rules} == {
        "long_regime",
        "pullback_resume",
    }
