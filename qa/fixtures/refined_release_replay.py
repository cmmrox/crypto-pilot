"""Offline release acceptance against the retained Binance dataset.

Checks every chronological decision through the public bot strategy entry point,
then compares the entire replay with the researched parameter configuration.
No database, credentials, network requests or order submission are involved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pandas as pd
from experiment_lab.adapters.artifacts import Artifacts
from experiment_lab.research.timeframe_replay import load_frames
from strategy_runtime.contracts import Candle, Intent, TradeState
from strategy_runtime.filters import SymbolFilters
from strategy_runtime.parameters import TrendRiderParameters
from strategy_runtime.refined_trend_rider import RefinedTrendRider
from strategy_runtime.replay import PluginReplayEngine, ReplayConfig

from app.strategies import get_strategy


class PublicPathCheck(RefinedTrendRider):
    """Exercise the same public on_candle entry point called by BotService."""

    def __init__(self, candles: list[Candle]) -> None:
        super().__init__()
        self.candles = candles
        self.production = get_strategy(self.manifest.strategy_id)
        self.checked = 0
        self.intent_counts: dict[str, int] = {}

    def on_prepared_frame(self, frame: pd.DataFrame, state: TradeState) -> list[Intent]:
        count = len(frame)
        history = self.manifest.market.history_bars
        actual = self.production.on_candle(
            self.candles[max(0, count - history) : count], state
        )
        expected = super().on_prepared_frame(frame, state)
        if actual != expected:
            raise AssertionError(
                f"Public/prepared decision mismatch at {frame.iloc[-1]['dt']}"
            )
        self.checked += 1
        for intent in actual:
            name = type(intent).__name__
            self.intent_counts[name] = self.intent_counts.get(name, 0) + 1
        return actual


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.dataset.read_bytes()
    data = json.loads(raw)
    if data["interval"] != "4h":
        raise ValueError("This release accepts only four-hour data")
    start, end = pd.Timestamp(data["start"]), pd.Timestamp(data["end"])
    candles, funding = load_frames(data, start, end)
    filters = SymbolFilters(
        **{key: Decimal(value) for key, value in data["filters"].items()}
    )
    config = ReplayConfig(
        parameters=TrendRiderParameters(trail_atr=4.5),
        initial_capital=Decimal("200"),
        long_fee_rate=Decimal("0.0006"),
        short_cost_rate=Decimal("0.0006"),
    )
    original = PluginReplayEngine(candles, funding, filters, config, start=start).run()
    replay = PluginReplayEngine(candles, funding, filters, config, start=start)
    candle_objects = [
        Candle(
            int(pd.Timestamp(str(row.dt)).timestamp() * 1000),
            float(str(row.open)),
            float(str(row.high)),
            float(str(row.low)),
            float(str(row.close)),
            float(str(row.volume)),
        )
        for row in candles.itertuples()
    ]
    checker = PublicPathCheck(candle_objects)
    replay.strategy = checker
    result = replay.run()
    pd.testing.assert_frame_equal(result.trades, original.trades, check_exact=True)
    pd.testing.assert_frame_equal(result.equity, original.equity, check_exact=True)
    pd.testing.assert_frame_equal(result.monthly, original.monthly, check_exact=True)
    assert result.final_equity == original.final_equity
    assert result.open_position == original.open_position
    if (
        args.dataset.stem
        == "b647dc3d1af717e21943b9a9cbbc00dbb76ffbac26a109d89d054d8177b1ec13"
    ):
        assert result.final_equity == Decimal("1643.200415351385582742800000")
        assert len(result.trades) == 105 and checker.checked == 6576
    root = Path(__file__).resolve().parents[2]
    sources = [
        *sorted((root / "packages/strategy_runtime/src/strategy_runtime").glob("*.py")),
        root / "backend/app/strategies/plugins/trend_rider_refined_v1_4h.py",
        root / "backend/app/bot/service.py",
        root / "backend/app/execution/orders.py",
        Path(__file__).resolve(),
    ]
    evidence = {
        "strategy_id": checker.manifest.strategy_id,
        "release": checker.manifest.release,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "public_closed_candle_decisions": checker.checked,
        "intent_counts": checker.intent_counts,
        "parameters": checker.params,
        "final_equity": str(result.final_equity),
        "closed_trades": len(result.trades),
        "open_position": result.open_position,
        "decision_mismatches": 0,
        "exact_equity_and_trade_match": True,
        "execution_model": "OHLC with production half-up protective-price tick rounding",
        "source_sha256": {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sources
        },
        "limitations": "OHLC simulated execution; no live-fill or profitability guarantee",
    }
    identity = Artifacts(args.output).put(evidence)
    print(json.dumps({"artifact": identity, **evidence}, indent=2))


if __name__ == "__main__":
    main()
