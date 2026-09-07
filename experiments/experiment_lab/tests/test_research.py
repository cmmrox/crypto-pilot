from dataclasses import replace
from decimal import Decimal

import pandas as pd
import pytest
from strategy_runtime.contracts import EnterLong, ExitAll, MoveStop, TradeState

from experiment_lab.research.regime_long import Parameters, RegimeLong
from experiment_lab.research.study import (
    coarse_candidates,
    neighbors,
    ranking,
    run_case,
)


def closed(**changes):
    return pd.Series(
        {
            "dt": pd.Timestamp("2024-03-01", tz="UTC"),
            "atr": 2,
            "close": 96,
            "research_center": 100,
            "research_channel": 110,
            "research_risk_on": True,
            **changes,
        }
    )


def test_pullback_only_enters_discounted_risk_on_market():
    strategy = RegimeLong(Parameters("pullback"))
    assert strategy.decide(closed(), TradeState(equity=200)) == [
        EnterLong(5, ((1.0, 0.5),), "pullback")
    ]
    assert strategy.decide(closed(research_risk_on=False), TradeState(equity=200)) == []
    assert strategy.decide(closed(close=100), TradeState(equity=200)) == []


def test_breaker_and_same_candle_close_block_reentry():
    strategy = RegimeLong(Parameters("pullback"))
    assert strategy.decide(closed(), TradeState(equity=200, halted_long=True)) == []
    ms = int(closed()["dt"].timestamp() * 1000)
    assert (
        strategy.decide(closed(), TradeState(equity=200, last_long_closed_at_ms=ms))
        == []
    )


def test_mean_recovery_exits_and_breakout_ratchets():
    state = TradeState(
        equity=200, long_position=True, highest_high=110, long_entry=100, tp1_done=True
    )
    assert RegimeLong(Parameters("pullback")).decide(closed(close=101), state) == [
        ExitAll("research_mean_recovered")
    ]
    assert RegimeLong(Parameters("breakout")).decide(closed(), state) == [MoveStop(102)]
    assert RegimeLong(Parameters("breakout")).decide(
        closed(research_risk_on=False), state
    ) == [ExitAll("research_regime_off")]


def test_indicator_preparation_does_not_read_future():
    frame = pd.DataFrame({"close": list(range(50, 350)), "high": list(range(52, 352))})
    strategy = RegimeLong(Parameters("breakout"))
    pd.testing.assert_frame_equal(
        strategy.prepare(frame.iloc[:240]), strategy.prepare(frame).iloc[:240]
    )
    assert (
        strategy.prepare(frame).iloc[100]["research_channel"] == frame.iloc[99]["high"]
    )


@pytest.mark.parametrize(
    "values",
    [{"stop_atr": float("nan")}, {"lookback": 0}, {"trail_atr": 8}, {"family": "grid"}],
)
def test_invalid_parameters_rejected(values):
    with pytest.raises(ValueError):
        replace(Parameters("pullback"), **values)


def test_search_is_bounded_and_refines_one_coordinate():
    candidates = coarse_candidates()
    assert len(candidates) == len(set(candidates)) == 24
    baseline = candidates[0]
    for candidate in neighbors(baseline):
        assert (
            sum(
                getattr(baseline, field) != getattr(candidate, field)
                for field in baseline.__dataclass_fields__
            )
            == 1
        )


def test_ranking_penalizes_flat_months_and_dangerous_profit():
    base = dict(
        net_profit="10",
        max_drawdown="-0.1",
        worst_month="-0.04",
        trade_count=50,
        profitable_months=14,
        full_months=24,
    )
    assert ranking(base) > ranking(
        {**base, "net_profit": "1000", "max_drawdown": "-0.8"}
    )
    assert ranking({**base, "profitable_months": 15}) > ranking(base)


def test_replay_is_deterministic_reconciles_and_executes_after_signal():
    times = pd.date_range("2024-01-01", periods=450, freq="4h", tz="UTC")
    candles = [
        {
            "dt": t.isoformat(),
            "open": str(100 + i),
            "close": str(103 + i),
            "high": str(104 + i),
            "low": str(99 + i),
            "volume": "1000",
        }
        for i, t in enumerate(times)
    ]
    data = {
        "candles": candles,
        "funding": [
            {
                "dt": times[405].isoformat(),
                "mark_price": "508",
                "funding_rate": "0.0001",
            }
        ],
        "filters": {
            "max_qty": "100",
            "min_qty": "0.001",
            "step_size": "0.001",
            "tick_size": "0.1",
            "min_notional": "5",
        },
    }
    # A genuine breakout candle, then its next open; all other closes below prior high.
    data["candles"][405].update(close="511", high="512")
    end = times[-1] + pd.Timedelta(hours=4)
    result = run_case(data, times[400], end, Parameters("breakout"))
    repeat = run_case(data, times[400], end, Parameters("breakout"))
    assert result == repeat
    assert Decimal(result["metrics"]["reconciliation_delta"]) == Decimal(0)
    invested = [row for row in result["equity"] if row["position"] == "LONG"]
    assert invested[0]["dt"] == times[406].isoformat()
    assert Decimal(result["metrics"]["fees_and_slippage"]) > 0
