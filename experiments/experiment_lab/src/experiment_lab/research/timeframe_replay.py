"""Timeframe-aware offline replay and immutable candidate descriptions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Literal

import pandas as pd
from strategy_runtime.filters import SymbolFilters
from strategy_runtime.parameters import (
    INTERVAL_MINUTES,
    TrendRiderParameters,
    validate_parameters,
)
from strategy_runtime.replay import PluginReplayEngine, ReplayConfig, config_dict

from experiment_lab.adapters.binance import validate_dataset
from experiment_lab.adapters.replay import records
from experiment_lab.research.regime_long import Parameters, RegimeLong
from experiment_lab.research.replay import ResearchReplay, summarize
from experiment_lab.research.timeframe_strategy import (
    AlignedTrendRider,
    align_completed_regime,
)


@dataclass(frozen=True)
class Candidate:
    interval: str
    family: Literal["trend", "aligned", "breakout"]
    parameters: dict[str, str]
    breakout_lookback: int = 40

    def __post_init__(self) -> None:
        if self.interval not in INTERVAL_MINUTES or self.family not in {
            "trend",
            "aligned",
            "breakout",
        }:
            raise ValueError("Unsupported research configuration")
        validate_parameters(self.parameters)
        if self.family == "breakout":
            Parameters("breakout", self.breakout_lookback)


def load_frames(
    data: dict[str, Any], start: pd.Timestamp, end: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Dataset JSON is heterogeneous; monetary strings stay Decimal in the shared engine.
    validate_dataset(data)
    if pd.Timestamp(data["start"]) > start or pd.Timestamp(data["end"]) < end:
        raise ValueError("Dataset does not cover the requested evaluation")
    frame = pd.DataFrame(data["candles"])
    frame = frame[pd.to_datetime(frame["dt"], utc=True) < end]
    funding = pd.DataFrame(data["funding"])
    times = pd.to_datetime(funding["dt"], utc=True, format="mixed")
    funding = funding[(times >= start) & (times < end)].copy()
    funding["mark_price"] = funding["mark_price"].map(
        lambda x: "NaN" if x is None or str(x).strip() == "" else x
    )
    return frame, funding


def run_candidate(
    data: dict[str, Any],
    higher: dict[str, Any],
    candidate: Candidate,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    cost: Decimal = Decimal("0.0006"),
    detailed: bool = False,
    capital: Decimal = Decimal("200"),
) -> dict[str, Any]:
    if data["interval"] != candidate.interval:
        raise ValueError("Candidate timeframe and market data differ")
    parameters = validate_parameters(candidate.parameters)
    values = TrendRiderParameters.from_values(parameters)
    config = ReplayConfig(
        parameters=values,
        interval=candidate.interval,
        initial_capital=capital,
        risk_pct=Decimal(parameters["risk_pct"]),
        leverage_cap=Decimal(parameters["leverage_cap"]),
        long_breaker_cap=Decimal(parameters["long_month_cap"]),
        short_breaker_cap=Decimal(parameters["sleeve_month_cap"]),
        long_fee_rate=cost,
        short_cost_rate=cost,
    )
    candles, funding = load_frames(data, start, end)
    filters = SymbolFilters(**{k: Decimal(v) for k, v in data["filters"].items()})
    engine: PluginReplayEngine
    if candidate.family == "breakout":
        engine = ResearchReplay(candles, funding, filters, config, start=start)
        engine.attach(
            RegimeLong(
                Parameters(
                    "breakout",
                    candidate.breakout_lookback,
                    0,
                    values.stop_atr,
                    values.trail_atr,
                )
            )
        )
    else:
        engine = PluginReplayEngine(candles, funding, filters, config, start=start)
        if candidate.family == "aligned":
            engine.df = align_completed_regime(
                engine.df, pd.DataFrame(higher["candles"]), candidate.interval
            )
            engine.strategy = AlignedTrendRider(values, candidate.interval)
    result = engine.run()
    metrics = summarize(engine, result, end)
    # The legacy summarizer annualizes at 4h. Correct only this research report;
    # production math remains untouched. Compare daily Sharpe across timeframes too.
    metrics["sharpe_interval"] = str(
        Decimal(metrics.pop("sharpe_4h"))
        * (Decimal(240) / INTERVAL_MINUTES[candidate.interval]).sqrt()
    )
    daily = result.equity.copy()
    daily["dt"] = pd.to_datetime(daily["dt"], utc=True)
    ends = daily.set_index("dt")["equity"].resample("1D").last().tolist()
    previous = capital
    returns = []
    for raw_value in ends:
        value = Decimal(str(raw_value))
        returns.append(float(value / previous - 1))
        previous = value
    series = pd.Series(returns)
    metrics["sharpe_daily"] = (
        str(Decimal(str(series.mean() / series.std(ddof=1) * 365**0.5)))
        if series.std(ddof=1) > 0
        else "0"
    )
    result_data = {
        "candidate": asdict(candidate),
        "effective_parameters": parameters,
        "account_config": config_dict(config),
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "metrics": metrics,
        "trades": records(result.trades),
    }
    if detailed:
        result_data["equity"] = records(result.equity)
        result_data["intents"] = records(pd.DataFrame(engine.intent_trace))
    return result_data
