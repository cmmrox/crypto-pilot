"""Unit tests for the strategy plugins and engine (QA-3)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from app.strategies import get_strategy, registered_names
from app.strategies.base import Candle, EnterLong, EnterShort, ExitAll, TradeState
from app.strategies.engine import add_indicators, run_composite, short_target


def _synthetic_bull(n: int = 260, start: float = 100.0) -> pd.DataFrame:
    """A steadily-rising series that establishes a bull regime."""
    closes = [start * (1.0 + 0.004) ** i for i in range(n)]
    rows = []
    for i, cl in enumerate(closes):
        rows.append(
            {
                "dt": pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(hours=4 * i),
                "open": cl * 0.999,
                "high": cl * 1.004,
                "low": cl * 0.996,
                "close": cl,
                "volume": 10.0,
            }
        )
    return pd.DataFrame(rows)


def _candles(df: pd.DataFrame) -> list[Candle]:
    return [
        Candle(
            open_time_ms=int(r["dt"].timestamp() * 1000),
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"],
        )
        for _, r in df.iterrows()
    ]


# --- Registry ---


def test_both_strategies_registered() -> None:
    assert "trend_rider_v6" in registered_names()
    assert "trend_rider_v52" in registered_names()


def test_get_unknown_strategy_raises() -> None:
    with pytest.raises(KeyError):
        get_strategy("does_not_exist")


def test_v6_params_are_validated_defaults() -> None:
    s = get_strategy("trend_rider_v6")
    assert s.params["stop_atr"] == 2.5
    assert s.params["tp1_frac"] == 0.4
    assert s.params["trail_atr"] == 4.0
    assert s.warmup_bars() == 200


# --- Indicators ---


def test_add_indicators_columns_and_regime() -> None:
    df = add_indicators(_synthetic_bull())
    for col in ("sma200", "ema20", "ema50", "ema200", "atr", "regime"):
        assert col in df.columns
    # A steadily-rising series is in a bull regime by the end.
    assert bool(df["regime"].iloc[-1])


def test_ema_matches_recursive_formula() -> None:
    df = add_indicators(_synthetic_bull(n=50))
    close = df["close"]
    alpha = 2 / (20 + 1)
    manual = close.iloc[0]
    for i in range(1, len(close)):
        manual = alpha * close.iloc[i] + (1 - alpha) * manual
    assert abs(float(df["ema20"].iloc[-1]) - manual) < 1e-6


# --- Rules ---


def test_warmup_returns_no_intents() -> None:
    s = get_strategy("trend_rider_v6")
    df = _synthetic_bull(n=50)
    intents = s.on_candle(_candles(df), TradeState(equity=10000.0))
    assert intents == []


def test_fresh_regime_emits_enter_long() -> None:
    s = get_strategy("trend_rider_v6")
    df = add_indicators(_synthetic_bull(n=300))
    # The fresh-regime signal fires on the first bar where regime flips True.
    regime = df["regime"].to_numpy()
    fresh_idx = next(i for i in range(1, len(regime)) if regime[i] and not regime[i - 1])
    candles = _candles(_synthetic_bull(n=300).iloc[: fresh_idx + 1])
    intents = s.on_candle(candles, TradeState(equity=10000.0))
    assert any(isinstance(i, EnterLong) for i in intents)
    el = next(i for i in intents if isinstance(i, EnterLong))
    assert el.stop_distance > 0
    assert el.tp_levels == ((1.0, 0.4),)


def test_regime_off_exits_long() -> None:
    s = get_strategy("trend_rider_v6")
    # Build a series that rises then crashes so the last bar is out of regime.
    up = _synthetic_bull(n=230)
    crash_rows = []
    last = up["close"].iloc[-1]
    for i in range(40):
        cl = last * (1 - 0.03) ** (i + 1)
        crash_rows.append(
            {
                "dt": up["dt"].iloc[-1] + pd.Timedelta(hours=4 * (i + 1)),
                "open": cl * 1.001,
                "high": cl * 1.002,
                "low": cl * 0.98,
                "close": cl,
                "volume": 10.0,
            }
        )
    df = pd.concat([up, pd.DataFrame(crash_rows)], ignore_index=True)
    intents = s.on_candle(_candles(df), TradeState(equity=10000.0, long_position=True))
    assert any(isinstance(i, ExitAll) for i in intents)


def test_v52_never_emits_short() -> None:
    s6 = get_strategy("trend_rider_v6")
    s52 = get_strategy("trend_rider_v52")
    # Deep-bear series.
    up = _synthetic_bull(n=210)
    crash_rows = []
    last = up["close"].iloc[-1]
    for i in range(60):
        cl = last * (1 - 0.02) ** (i + 1)
        crash_rows.append(
            {
                "dt": up["dt"].iloc[-1] + pd.Timedelta(hours=4 * (i + 1)),
                "open": cl,
                "high": cl * 1.005,
                "low": cl * 0.99,
                "close": cl,
                "volume": 10.0,
            }
        )
    df = pd.concat([up, pd.DataFrame(crash_rows)], ignore_index=True)
    candles = _candles(df)
    v6_intents = s6.on_candle(candles, TradeState(equity=10000.0))
    v52_intents = s52.on_candle(candles, TradeState(equity=10000.0))
    # v6 may short in deep bear; v52 must never.
    assert not any(isinstance(i, EnterShort) for i in v52_intents)
    _ = v6_intents  # v6 behaviour asserted elsewhere/parity


def test_determinism_same_input_same_output() -> None:
    s = get_strategy("trend_rider_v6")
    df = _synthetic_bull()
    candles = _candles(df)
    a = s.on_candle(candles, TradeState(equity=10000.0))
    b = s.on_candle(candles, TradeState(equity=10000.0))
    assert a == b


def test_run_composite_is_deterministic() -> None:
    df = pd.DataFrame(_synthetic_bull())
    r1 = run_composite(df).equity.to_numpy()
    r2 = run_composite(df).equity.to_numpy()
    assert np.array_equal(r1, r2)


def test_short_target_is_zero_in_bull() -> None:
    df = add_indicators(_synthetic_bull())
    assert float(short_target(df).iloc[-1]) == 0.0
