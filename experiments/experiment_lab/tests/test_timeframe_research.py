from dataclasses import asdict
from decimal import Decimal

import pandas as pd
import pytest
from strategy_runtime.contracts import (
    EnterLong,
    EnterShort,
    ExitAll,
    MoveStop,
    TradeState,
)
from strategy_runtime.parameters import TrendRiderParameters, validate_parameters
from strategy_runtime.trend_rider import TrendRider
from strategy_runtime.filters import SymbolFilters
from strategy_runtime.replay import PluginReplayEngine, ReplayConfig

from experiment_lab.research.timeframe_replay import Candidate
from experiment_lab.research.reconcile_candles import aggregate_minutes
from experiment_lab.research.timeframe_strategy import (
    AlignedTrendRider,
    align_completed_regime,
)
from experiment_lab.research.timeframe_study import ranking, refine, universe


def higher_frame():
    times = pd.date_range("2024-01-01", periods=260, freq="4h", tz="UTC")
    return pd.DataFrame(
        {
            "dt": times,
            "open": range(100, 360),
            "high": range(102, 362),
            "low": range(99, 359),
            "close": range(101, 361),
            "volume": 100,
        }
    )


def test_four_hour_signal_is_not_available_before_its_close():
    high = higher_frame()
    boundary = high.iloc[230]["dt"] + pd.Timedelta(hours=4)
    lower = pd.DataFrame(
        {"dt": [boundary - pd.Timedelta(hours=1), boundary - pd.Timedelta(minutes=30)]}
    )
    aligned = align_completed_regime(lower, high, "30m")
    assert aligned.iloc[0]["known_at"] == boundary - pd.Timedelta(hours=4)
    assert aligned.iloc[1]["known_at"] == boundary
    assert (aligned["known_at"] <= aligned["decision_at"]).all()


def test_future_higher_timeframe_prices_cannot_change_earlier_decisions():
    high = higher_frame()
    lower = pd.DataFrame(
        {"dt": pd.date_range(high.iloc[220]["dt"], periods=20, freq="30min", tz="UTC")}
    )
    original = align_completed_regime(lower, high, "30m")
    changed = high.copy()
    changed.loc[230:, ["open", "high", "low", "close"]] = 10
    pd.testing.assert_frame_equal(
        original, align_completed_regime(lower, changed, "30m")
    )


def test_missing_higher_timeframe_information_blocks_entries():
    high = higher_frame()
    lower = pd.DataFrame({"dt": [high.iloc[0]["dt"]]})
    aligned = align_completed_regime(lower, high, "1h")
    assert not aligned.iloc[0]["htf_long_allowed"]
    assert not aligned.iloc[0]["htf_short_allowed"]


def test_higher_timeframe_filter_preserves_exit_and_stop_management(monkeypatch):
    intents = [
        EnterLong(5, ((1, 0.4),)),
        EnterShort(0.5, 0.4),
        ExitAll("regime off"),
        MoveStop(100),
    ]
    monkeypatch.setattr(
        TrendRider, "on_prepared_frame", lambda self, df, state: intents
    )
    strategy = AlignedTrendRider(TrendRiderParameters(), "1h")
    frame = pd.DataFrame({"htf_long_allowed": [False], "htf_short_allowed": [False]})
    assert strategy.on_prepared_frame(frame, TradeState(equity=200)) == intents[2:]
    assert strategy.manifest.validation.status == "unverified"
    assert not strategy.manifest.packaged_default


def test_candidate_grid_is_bounded_and_refinement_does_not_raise_risk():
    candidates = universe()
    assert len(candidates) == 57
    assert len({str(asdict(c)) for c in candidates}) == 57
    for original in candidates:
        for candidate in refine(original):
            before = validate_parameters(original.parameters)
            after = validate_parameters(candidate.parameters)
            assert before["risk_pct"] == after["risk_pct"]
            assert before["leverage_cap"] == after["leverage_cap"]
            assert before["long_month_cap"] == after["long_month_cap"]


@pytest.mark.parametrize("interval", ["5m", "1d", "unknown"])
def test_unsupported_timeframes_fail(interval):
    with pytest.raises(ValueError):
        Candidate(interval, "trend", {})


def test_profit_ranking_does_not_reward_a_catastrophic_training_result():
    metrics = {
        "net_profit": "100",
        "max_drawdown": "-0.3",
        "worst_month": "-0.1",
        "trade_count": 50,
        "monthly": [{"profit": "1"} for _ in range(24)],
    }
    assert ranking(metrics) == (True, Decimal("100"))
    assert ranking(metrics) > ranking(
        {**metrics, "net_profit": "10000", "max_drawdown": "-0.9"}
    )


@pytest.mark.parametrize("interval,minutes", [("30m", 30), ("1h", 60), ("4h", 240)])
def test_funding_bar_uses_minutes_not_pandas_month_alias(interval, minutes):
    frame = higher_frame()
    frame["dt"] = pd.date_range(
        "2024-01-01", periods=len(frame), freq=pd.Timedelta(minutes=minutes), tz="UTC"
    )
    timestamp = frame.iloc[220]["dt"]
    funding = pd.DataFrame(
        [
            {
                "dt": timestamp + pd.Timedelta(milliseconds=1),
                "mark_price": "300",
                "funding_rate": "0.0001",
            }
        ]
    )
    filters = SymbolFilters(
        Decimal("0.1"), Decimal("0.001"), Decimal("100"), Decimal("0.001"), Decimal("5")
    )
    engine = PluginReplayEngine(
        frame, funding, filters, ReplayConfig(interval=interval), start=timestamp
    )
    assert engine.funding.iloc[0]["bar_open"] == timestamp


def test_30m_resampling_means_thirty_minutes_not_month_end():
    times = pd.date_range("2024-01-01", periods=60, freq="min", tz="UTC")
    raw = [[int(t.timestamp() * 1000), "100", "102", "99", "101", "1"] for t in times]
    bars = aggregate_minutes(raw, "30m")
    assert len(bars) == 2
    assert bars.index[1] == times[30]
    assert bars.iloc[0]["volume"] == Decimal("30")
    with pytest.raises(ValueError):
        aggregate_minutes(raw[:-1], "30m")


def test_profit_refinement_locks_training_selection_before_later_results(
    monkeypatch, tmp_path
):
    from experiment_lab.adapters.artifacts import Artifacts
    from experiment_lab.research import profit_refinement

    events = []
    monkeypatch.setattr(
        profit_refinement, "read_dataset", lambda path: {"interval": "4h"}
    )
    monkeypatch.setattr(profit_refinement, "code_hash", lambda: "test-only")
    monkeypatch.setattr(
        profit_refinement, "event", lambda name, **fields: events.append(name)
    )

    def replay(data, higher, candidate, start, end, **options):
        values = validate_parameters(candidate.parameters)
        if end == profit_refinement.END:
            assert "profit_refinement_locked" in events
        profit = "120" if values["trail_atr"] == "4.5" else "100"
        if values["tp1_frac"] == "0.2":
            profit, drawdown = "10000", "-0.9"
        else:
            drawdown = "-0.3"
        return {"metrics": {"net_profit": profit, "max_drawdown": drawdown}}

    monkeypatch.setattr(profit_refinement, "run_candidate", replay)
    report_id = profit_refinement.execute(
        tmp_path / "dataset.json", tmp_path / "artifacts"
    )
    report = Artifacts(tmp_path / "artifacts").get(report_id)
    assert report["trial_count"] == 16
    assert report["winner"]["candidate"]["parameters"]["trail_atr"] == "4.5"
    assert report["winner"]["candidate"]["parameters"]["tp1_frac"] != "0.2"
    assert report["deterministic_repeat"] == "PASS"
    assert report["suitable_for_live"] is False
