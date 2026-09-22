"""Atlas 7 Dual rule tests: pure, deterministic, closed-candle behaviour.

Series are built explicitly so each rule is exercised on its own; the chronological
bot replay over real candles lives in tests/integration/test_atlas_dual_release.py.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from app.strategies import EnterLong, EnterShortStop, ExitAll, MoveStop, TradeState
from strategy_runtime.atlas_dual import AtlasDual, AtlasDualParameters, add_indicators
from strategy_runtime.contracts import Candle

WARMUP = AtlasDual.manifest.market.warmup_bars
FLAT = TradeState(equity=10_000.0)


def _candle(index: int, close: float, previous: float) -> Candle:
    """One 4h candle that opens at the previous close (so true range is real)."""
    return Candle(
        open_time_ms=1_700_000_000_000 + index * 14_400_000,
        open=previous,
        high=max(previous, close),
        low=min(previous, close),
        close=close,
        volume=10.0,
    )


def _series(closes: list[float]) -> list[Candle]:
    out: list[Candle] = []
    previous = closes[0]
    for index, close in enumerate(closes):
        out.append(_candle(index, close, previous))
        previous = close
    return out


def _noisy_base(bars: int, level: float = 100.0, amplitude: float = 3.0) -> list[float]:
    """A wide sideways base: gives ATR a real value and a wide range-width history."""
    return [level + (amplitude if i % 2 else -amplitude) for i in range(bars)]


def _bull_series() -> list[float]:
    """Wide base, then a rally that establishes the bull regime."""
    return _noisy_base(WARMUP) + [100.0 + i * 1.5 for i in range(1, 61)]


def _bear_series() -> list[float]:
    return _noisy_base(WARMUP) + [100.0 - i * 1.5 for i in range(1, 61)]


def _indicators(closes: list[float]):
    import pandas as pd

    candles = _series(closes)
    frame = pd.DataFrame(
        {
            "dt": [c.open_time_ms for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
        }
    )
    return add_indicators(frame, AtlasDualParameters())


def _strategy() -> AtlasDual:
    return AtlasDual()


def test_no_intent_before_warmup() -> None:
    candles = _series(_noisy_base(WARMUP - 1))
    assert _strategy().on_candle(candles, FLAT) == []
    assert _strategy().inspect(candles) is None


def test_fresh_bull_regime_opens_a_long_with_stop_and_target() -> None:
    # A wide sideways base, then one close that clears SMA200 + 1 ATR with EMA50 on top.
    closes = [*_noisy_base(WARMUP), 150.0]
    df = _indicators(closes)
    assert bool(df.iloc[-1]["bull"]) and not bool(df.iloc[-2]["bull"])  # regime just began
    intents = _strategy().on_candle(_series(closes), FLAT)
    assert len(intents) == 1
    entry = intents[0]
    assert isinstance(entry, EnterLong)
    assert entry.stop_distance > 0
    assert entry.tp_levels == ((2.0, 0.4),)


def test_bear_regime_opens_a_stop_protected_short() -> None:
    closes = [*_noisy_base(WARMUP), 50.0]
    assert bool(_indicators(closes).iloc[-1]["bear"])
    intents = _strategy().on_candle(_series(closes), FLAT)
    assert len(intents) == 1
    entry = intents[0]
    assert isinstance(entry, EnterShortStop)  # never the stop-free sleeve
    assert entry.stop_distance > 0


def test_hysteresis_band_blocks_entries_around_the_slow_average() -> None:
    """A close above SMA200 but inside the 1 ATR buffer must not open a trade."""
    base = _noisy_base(WARMUP)
    row = _indicators(base).iloc[-1]
    inside_band = float(row["sma_slow"]) + 0.5 * float(row["atr"])
    closes = [*base, inside_band]
    assert not bool(_indicators(closes).iloc[-1]["bull"])
    assert _strategy().on_candle(_series(closes), FLAT) == []


def test_squeeze_breakout_enters_after_a_tight_range() -> None:
    """A wide history, a bull regime, then a tight range broken to the upside."""
    rally = [100.0 + i * 1.5 for i in range(1, 61)]  # establishes the bull regime
    quiet = [rally[-1] + (0.05 if i % 2 else -0.05) for i in range(30)]  # the squeeze
    closes = _noisy_base(WARMUP) + rally + quiet
    df = _indicators(closes)
    assert bool(df.iloc[-1]["was_tight"]) and bool(df.iloc[-1]["bull"])
    breakout = max(closes[-30:]) + 8.0
    intents = _strategy().on_candle(_series([*closes, breakout]), FLAT)
    assert any(isinstance(i, EnterLong) and i.reason == "squeeze breakout" for i in intents)


def test_regime_exit_closes_the_long() -> None:
    closes = _bull_series()
    long_state = replace(FLAT, long_position=True, long_entry=180.0, long_stop=170.0)
    crashed = [*closes, 60.0]
    intents = _strategy().on_candle(_series(crashed), long_state)
    assert [type(i) for i in intents] == [ExitAll]
    assert isinstance(intents[0], ExitAll) and intents[0].reason == "regime exit"


def test_long_trail_waits_for_the_first_target_then_ratchets() -> None:
    candles = _series(_bull_series())
    holding = replace(
        FLAT, long_position=True, long_entry=180.0, long_stop=170.0, highest_high=230.0
    )
    assert _strategy().on_candle(candles, holding) == []  # no partial yet: stop stays
    after_tp = replace(holding, tp1_done=True)
    intents = _strategy().on_candle(candles, after_tp)
    assert len(intents) == 1 and isinstance(intents[0], MoveStop)
    assert intents[0].price > 170.0
    # Never loosens: an existing stop above the trail level is kept.
    atr = float(_indicators(_bull_series()).iloc[-1]["atr"])
    tight = replace(after_tp, long_stop=230.0 - 3.0 * atr + 1.0, highest_high=230.0)
    assert _strategy().on_candle(candles, tight) == []


def test_short_trail_only_moves_down() -> None:
    candles = _series(_bear_series())
    holding = replace(
        FLAT,
        short_position=True,
        short_entry=40.0,
        short_stop=52.0,
        lowest_low=20.0,
        tp1_done=True,
    )
    intents = _strategy().on_candle(candles, holding)
    assert len(intents) == 1 and isinstance(intents[0], MoveStop)
    assert intents[0].price < 52.0
    atr = float(_indicators(_bear_series()).iloc[-1]["atr"])
    already_tight = replace(holding, short_stop=20.0 + 3.0 * atr - 1.0)
    assert _strategy().on_candle(candles, already_tight) == []


def test_reversal_exits_then_enters_the_other_side() -> None:
    """A fresh bear signal while long: flatten first, then open the short."""
    closes = [*_noisy_base(WARMUP), 50.0]
    long_state = replace(FLAT, long_position=True, long_entry=104.0, long_stop=98.0)
    intents = _strategy().on_candle(_series(closes), long_state)
    assert [type(i) for i in intents] == [ExitAll, EnterShortStop]
    assert isinstance(intents[0], ExitAll) and intents[0].reason in {
        "regime exit",
        "reverse to short",
    }


def test_reversal_is_blocked_while_that_side_is_halted() -> None:
    closes = [*_noisy_base(WARMUP), 50.0]
    long_state = replace(
        FLAT, long_position=True, long_entry=104.0, long_stop=98.0, halted_short=True
    )
    intents = _strategy().on_candle(_series(closes), long_state)
    assert [type(i) for i in intents] == [ExitAll]


def test_halts_block_only_their_own_side() -> None:
    bull = _series([*_noisy_base(WARMUP), 150.0])
    bear = _series([*_noisy_base(WARMUP), 50.0])
    assert _strategy().on_candle(bull, replace(FLAT, halted_long=True)) == []
    assert _strategy().on_candle(bear, replace(FLAT, halted_short=True)) == []
    assert _strategy().on_candle(bull, replace(FLAT, halted_short=True)) != []


def test_is_deterministic_and_pure() -> None:
    candles = _series([*_noisy_base(WARMUP), 150.0])
    first = _strategy().on_candle(candles, FLAT)
    second = _strategy().on_candle(candles, FLAT)
    assert first == second
    # the same instance twice, and the candle list is untouched
    strategy = _strategy()
    snapshot = list(candles)
    strategy.on_candle(candles, FLAT)
    assert candles == snapshot


def test_manifest_pins_the_owner_selected_risk_profile() -> None:
    risk = AtlasDual.manifest.risk
    assert str(risk.long_risk_pct) == "4"
    assert str(risk.leverage_cap) == "3"
    assert str(risk.long_monthly_loss_cap) == "0.08"
    assert str(risk.short_monthly_loss_cap) == "0.08"
    assert AtlasDual.manifest.market.interval == "4h"
    assert AtlasDual.manifest.market.decision_point == "closed_candle"
    assert AtlasDual.manifest.packaged_default is False


def test_parameters_are_pinned() -> None:
    values = AtlasDualParameters().values()
    assert values["stop_atr"] == 2.5
    assert values["tp1_r"] == 2.0
    assert values["tp1_frac"] == 0.4
    assert values["trail_atr"] == 3.0
    assert values["hysteresis_atr"] == 1.0
    assert values["range_bars"] == 24
    assert values["width_lookback"] == 360


def test_inspect_reports_rules_after_warmup() -> None:
    candles = _series(_bull_series())
    watch = _strategy().inspect(candles)
    assert watch is not None
    keys = [rule.key for rule in watch.rules]
    assert keys == ["regime", "pullback", "squeeze"]
    assert watch.last_closed_open_time_ms == candles[-1].open_time_ms
    assert "closed 4h candle" in watch.disclaimer


@pytest.mark.parametrize("bars", [WARMUP, WARMUP + 1])
def test_warmup_boundary(bars: int) -> None:
    # A sideways base at the warm-up boundary: evaluated, but no regime, no signal.
    assert _strategy().on_candle(_series(_noisy_base(bars)), FLAT) == []


def test_pullback_is_traded_once_per_book() -> None:
    """After a position closes, the same old pullback must not re-arm an entry."""
    rally = [100.0 + i * 1.5 for i in range(1, 61)]
    # EMA20 sits ~14 below the last close here, so dip clearly under it, then recover.
    dip = [rally[-1] - 20.0, rally[-1] - 24.0]
    recovery = [rally[-1] - 2.0, rally[-1] + 1.0]
    closes = [*_noisy_base(WARMUP), *rally, *dip, *recovery]
    candles = _series(closes)
    df = _indicators(closes)
    assert closes[-4] < float(df.iloc[-4]["ema_fast"]), "the dip must close below EMA20"
    assert closes[-1] > float(df.iloc[-1]["ema_fast"]), "price must close back above EMA20"
    intents = _strategy().on_candle(candles, FLAT)
    assert any(isinstance(i, EnterLong) and i.reason == "pullback resume" for i in intents), (
        "the pullback must arm an entry"
    )
    # A long that closed after that pullback consumes it: no immediate re-entry.
    closed_after_pullback = candles[-1].open_time_ms
    used = replace(FLAT, last_long_closed_at_ms=closed_after_pullback)
    assert _strategy().on_candle(candles, used) == []
    # A long that closed *before* the pullback leaves it available.
    stale = replace(FLAT, last_long_closed_at_ms=candles[-6].open_time_ms)
    assert any(
        isinstance(i, EnterLong) and i.reason == "pullback resume"
        for i in _strategy().on_candle(candles, stale)
    )
