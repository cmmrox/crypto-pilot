"""Both production and prepared replay entrypoints must honor plugin identity."""

from dataclasses import replace

import pandas as pd
import pytest
from app.strategies import Candle, TradeState, get_strategy, registered_names
from strategy_runtime.indicators import add_indicators
from strategy_runtime.trend_rider import _to_frame


@pytest.mark.parametrize("strategy_id", registered_names())
@pytest.mark.parametrize("direction", [1, -1])
def test_public_and_prepared_paths_agree(strategy_id: str, direction: int) -> None:
    strategy = get_strategy(strategy_id)
    candles = [
        Candle(
            i * 14_400_000,
            1000 + direction * i,
            1002 + direction * i,
            998 + direction * i,
            1000 + direction * i,
            10,
        )
        for i in range(320)
    ]
    frame: pd.DataFrame = add_indicators(_to_frame(candles), strategy.parameters)
    flat = TradeState(equity=200)
    states = [
        flat,
        replace(flat, halted_long=True, halted_short=True),
        replace(
            flat,
            long_position=True,
            long_entry=1000,
            long_stop=900,
            highest_high=1400,
            tp1_done=True,
        ),
    ]
    for state in states:
        assert strategy.on_candle(candles, state) == strategy.on_prepared_frame(frame, state)
