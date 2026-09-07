"""Release identity, parameter pins and public decision-path equivalence."""

from dataclasses import FrozenInstanceError

import pytest
from app.strategies import get_strategy
from app.strategies.base import MoveStop, TradeState
from app.strategies.catalog import default_strategy
from strategy_runtime.indicators import add_indicators
from strategy_runtime.parameters import TrendRiderParameters
from strategy_runtime.refined_trend_rider import RefinedTrendRider
from strategy_runtime.trend_rider import TrendRider

from tests.unit.test_strategies import _candles, _synthetic_bull

REFINED = "trend_rider_refined_v1_4h"


def test_refined_is_separate_without_changing_original_or_default() -> None:
    refined = get_strategy(REFINED)
    original = get_strategy("trend_rider_v6_4h")
    assert isinstance(refined, RefinedTrendRider)
    assert refined.params == {**original.params, "trail_atr": 4.5}
    assert original.params["trail_atr"] == 4
    assert default_strategy() is original
    assert get_strategy("trend_rider_v6") is original
    assert refined.manifest.legacy_ids == ()
    assert refined.manifest.release == "1.0"
    assert refined.manifest.market == original.manifest.market
    assert refined.manifest.risk == original.manifest.risk
    assert refined.manifest.capabilities == original.manifest.capabilities


def test_release_pins_every_parameter_and_rejects_constructor_overrides() -> None:
    refined = RefinedTrendRider()
    assert refined.params == {
        "stop_atr": 2.5,
        "tp1_r": 1,
        "tp1_frac": 0.4,
        "trail_atr": 4.5,
        "sleeve_depth_atr": 0.5,
        "sleeve_vol_target": 0.4,
        "sleeve_weight": 0.75,
        "sleeve_vol_span": 48,
        "fast_period": 20,
        "medium_period": 50,
        "slow_period": 200,
        "atr_period": 14,
        "risk_pct": 15,
        "leverage_cap": 6,
        "long_month_cap": 0.04,
        "sleeve_month_cap": 0.04,
    }
    with pytest.raises(TypeError):
        RefinedTrendRider(TrendRiderParameters())  # type: ignore[call-arg]
    with pytest.raises(FrozenInstanceError):
        refined.parameters.trail_atr = 4  # type: ignore[misc]


@pytest.mark.parametrize("bars", [50, 199, 200, 260])
@pytest.mark.parametrize(
    "state",
    [
        TradeState(equity=200),
        TradeState(equity=200, halted_long=True, halted_short=True),
        TradeState(equity=200, short_weight=0.5),
        TradeState(equity=200, long_position=True, tp1_done=False),
        TradeState(
            equity=200,
            long_position=True,
            tp1_done=True,
            long_entry=100,
            long_stop=100,
            highest_high=400,
        ),
    ],
)
def test_public_closed_candle_path_matches_research_configuration(
    bars: int,
    state: TradeState,
) -> None:
    candles = _candles(_synthetic_bull(bars))
    release = RefinedTrendRider()
    research = TrendRider(TrendRiderParameters(trail_atr=4.5))
    expected = research.on_candle(candles, state)
    assert release.on_candle(candles, state) == expected
    assert release.on_candle(candles, state) == expected
    assert release.inspect(candles) == research.inspect(candles)


def test_refined_trail_is_wider_and_never_lowers_existing_stop() -> None:
    frame = _synthetic_bull()
    candles = _candles(frame)
    atr = float(add_indicators(frame)["atr"].iloc[-1])
    state = TradeState(
        equity=200,
        long_position=True,
        tp1_done=True,
        long_entry=100,
        long_stop=100,
        highest_high=400,
    )
    assert RefinedTrendRider().on_candle(candles, state) == [MoveStop(400 - 4.5 * atr)]
    assert TrendRider().on_candle(candles, state) == [MoveStop(400 - 4 * atr)]
    state.long_stop = 500
    assert RefinedTrendRider().on_candle(candles, state) == []
