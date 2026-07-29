from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from app.execution.filters import SymbolFilters
from trend_rider_lab.asymmetric_30m import (
    Window,
    _group_starts,
    _selected_candidates,
)
from trend_rider_lab.live_path_audit import audit
from trend_rider_lab.replay import (
    PluginReplayEngine,
    Position,
    ReferenceReplayEngine,
    ReplayConfig,
    _production_tp_qty,
    run_replay,
)
from trend_rider_lab.search_30m import (
    Market,
    broad_candidates,
    download_30m_dataset,
    download_intraday_dataset,
    refined_candidates,
    strategy_returns,
)


def test_tp_quantity_is_exchange_valid_and_never_exceeds_position() -> None:
    filters = SymbolFilters(
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        max_qty=Decimal("120"),
        tick_size=Decimal("0.10"),
        min_notional=Decimal("50"),
    )
    assert _production_tp_qty(Decimal("0.009"), Decimal("0.4"), filters) == Decimal(
        "0.004"
    )
    assert _production_tp_qty(Decimal("0.001"), Decimal("0.4"), filters) == Decimal("0")


def test_replay_is_deterministic_on_flat_warmup_fixture() -> None:
    timestamps = pd.date_range("2023-01-01", periods=260, freq="4h", tz="UTC")
    candles = pd.DataFrame(
        {
            "open_time_ms": [int(ts.timestamp() * 1000) for ts in timestamps],
            "dt": timestamps,
            "open": ["100"] * len(timestamps),
            "high": ["100"] * len(timestamps),
            "low": ["100"] * len(timestamps),
            "close": ["100"] * len(timestamps),
            "volume": ["1"] * len(timestamps),
            "close_time_ms": [
                int(ts.timestamp() * 1000) + 14_399_999 for ts in timestamps
            ],
        }
    )
    funding = pd.DataFrame(
        columns=["funding_time_ms", "dt", "funding_rate", "mark_price"]
    )
    filters = SymbolFilters(
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        max_qty=Decimal("120"),
        tick_size=Decimal("0.10"),
        min_notional=Decimal("50"),
    )
    config = ReplayConfig()
    start = timestamps[220]
    first = run_replay(candles, funding, filters, config, start=start)
    second = run_replay(candles, funding, filters, config, start=start)
    assert first.final_equity == Decimal("100")
    assert first.final_equity == second.final_equity
    assert first.trades.empty


def test_replay_accepts_mixed_iso_funding_precision() -> None:
    timestamps = pd.date_range("2023-01-01", periods=240, freq="4h", tz="UTC")
    candles = pd.DataFrame(
        {
            "open_time_ms": [int(ts.timestamp() * 1000) for ts in timestamps],
            "dt": timestamps,
            "open": ["100"] * len(timestamps),
            "high": ["100"] * len(timestamps),
            "low": ["100"] * len(timestamps),
            "close": ["100"] * len(timestamps),
            "volume": ["1"] * len(timestamps),
            "close_time_ms": [
                int(ts.timestamp() * 1000) + 14_399_999 for ts in timestamps
            ],
        }
    )
    funding = pd.DataFrame(
        {
            "funding_time_ms": [int(timestamps[221].timestamp() * 1000)],
            "dt": [
                (timestamps[221] + pd.Timedelta(milliseconds=1)).isoformat(
                    timespec="milliseconds"
                )
            ],
            "funding_rate": ["0.0001"],
            "mark_price": [float("nan")],
        }
    )
    filters = SymbolFilters(
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        max_qty=Decimal("120"),
        tick_size=Decimal("0.10"),
        min_notional=Decimal("50"),
    )
    result = run_replay(
        candles, funding, filters, ReplayConfig(), start=timestamps[220]
    )
    assert result.final_equity == Decimal("100")


def test_replay_rejects_candle_gaps() -> None:
    timestamps = list(pd.date_range("2023-01-01", periods=240, freq="4h", tz="UTC"))
    del timestamps[210]
    candles = pd.DataFrame(
        {
            "dt": timestamps,
            "open": ["100"] * len(timestamps),
            "high": ["100"] * len(timestamps),
            "low": ["100"] * len(timestamps),
            "close": ["100"] * len(timestamps),
            "volume": ["1"] * len(timestamps),
        }
    )
    funding = pd.DataFrame(
        columns=["funding_time_ms", "dt", "funding_rate", "mark_price"]
    )
    filters = SymbolFilters(
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        max_qty=Decimal("120"),
        tick_size=Decimal("0.10"),
        min_notional=Decimal("50"),
    )
    with pytest.raises(ValueError, match="continuous 4h"):
        run_replay(candles, funding, filters, ReplayConfig(), start=timestamps[220])


def test_live_path_audit_passes_for_runtime_equivalence_requirements() -> None:
    repo = Path(__file__).resolve().parents[3]
    result = audit(repo)
    assert "EnterLong" in result.handled_intents
    assert "EnterShort" in result.handled_intents
    assert "ExitAll" in result.handled_intents
    assert result.missing_intents == ()
    assert result.breaker_state_connected is True
    assert result.long_trade_state_connected is True
    assert result.validated_trailing_high_connected is True
    assert result.specific_order_management_available is True
    assert result.fill_sync_available is True
    assert result.flatten_closes_trade_record is True
    assert result.safe_mode_manages_open_positions is True
    assert result.next_open_execution_available is True
    assert result.passed is True


def test_monthly_breaker_accumulates_incremental_bar_deltas() -> None:
    class HeldShortReplay(ReferenceReplayEngine):
        def _process_open(self, i, row, prev):  # type: ignore[no-untyped-def]
            del i, row, prev

        def _process_intrabar(self, i, row):  # type: ignore[no-untyped-def]
            del i, row

        def _update_signal_memory(self, row, prev):  # type: ignore[no-untyped-def]
            del row, prev

    timestamps = pd.date_range("2024-01-01", periods=230, freq="4h", tz="UTC")
    prices = [Decimal("100")] * 220 + [
        Decimal("100") + Decimal(index) / Decimal("3") for index in range(10)
    ]
    candles = pd.DataFrame(
        {
            "dt": timestamps,
            "open": prices,
            "high": [price + Decimal("0.1") for price in prices],
            "low": [price - Decimal("0.1") for price in prices],
            "close": prices,
            "volume": [Decimal("1")] * len(prices),
        }
    )
    filters = SymbolFilters(
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        max_qty=Decimal("120"),
        tick_size=Decimal("0.10"),
        min_notional=Decimal("50"),
    )
    replay = HeldShortReplay(
        candles,
        pd.DataFrame(columns=["funding_time_ms", "dt", "funding_rate", "mark_price"]),
        filters,
        ReplayConfig(funding_enabled=False),
        start=timestamps[220],
    )
    replay.position = Position(
        side="SHORT",
        qty=Decimal("1"),
        entry_price=Decimal("100"),
        opened_at=timestamps[220],
        entry_equity=Decimal("100"),
        entry_fee=Decimal("0"),
    )

    result = replay.run()

    assert result.short_breaker_trips == 0
    assert result.final_equity > Decimal("96")


def test_plugin_replay_matches_reference_on_regime_transition_fixture() -> None:
    timestamps = pd.date_range("2023-01-01", periods=500, freq="4h", tz="UTC")
    prices: list[Decimal] = []
    price = Decimal("100")
    for index in range(500):
        rate = (
            Decimal("1.004")
            if index < 250
            else Decimal("0.99")
            if index < 400
            else Decimal("1.01")
        )
        price *= rate
        prices.append(price)
    candles = pd.DataFrame(
        {
            "dt": timestamps,
            "open": prices,
            "high": [price * Decimal("1.004") for price in prices],
            "low": [price * Decimal("0.996") for price in prices],
            "close": prices,
            "volume": [Decimal("1")] * len(prices),
        }
    )
    funding = pd.DataFrame(
        columns=["funding_time_ms", "dt", "funding_rate", "mark_price"]
    )
    filters = SymbolFilters(
        step_size=Decimal("0.0001"),
        min_qty=Decimal("0.0001"),
        max_qty=Decimal("120"),
        tick_size=Decimal("0.01"),
        min_notional=Decimal("1"),
    )
    config = ReplayConfig(funding_enabled=False)
    reference = ReferenceReplayEngine(
        candles, funding, filters, config, start=timestamps[220]
    ).run()
    plugin = PluginReplayEngine(
        candles, funding, filters, config, start=timestamps[220]
    ).run()

    columns = ["side", "opened_at", "closed_at", "exit_reason"]
    assert reference.trades[columns].equals(plugin.trades[columns])
    assert abs(reference.final_equity - plugin.final_equity) < Decimal("1e-10")
    assert reference.long_breaker_trips == plugin.long_breaker_trips
    assert reference.short_breaker_trips == plugin.short_breaker_trips


def test_30m_search_generates_deterministic_unique_candidates() -> None:
    first = broad_candidates(1_000)
    second = broad_candidates(1_000)

    assert first == second
    assert len(first) == len(set(first)) == 1_000
    assert {candidate.family for candidate in first} == {
        "ema",
        "momentum",
        "donchian",
        "channel",
        "mean_reversion",
        "ensemble",
    }


def test_30m_refinement_changes_valid_parameters_near_leaders() -> None:
    leaders = broad_candidates(50)[:10]
    refined = refined_candidates(leaders, 100)

    assert len(refined) == len(set(refined)) == 100
    assert not set(refined).intersection(leaders)


def test_30m_returns_execute_signal_at_next_open() -> None:
    timestamps = pd.date_range("2026-01-01", periods=4, freq="30min", tz="UTC")
    market = Market(
        frame=pd.DataFrame(),
        timestamps=timestamps,
        open_=np.array([100.0, 110.0, 121.0, 133.1]),
        high=np.array([100.0, 110.0, 121.0, 133.1]),
        low=np.array([100.0, 110.0, 121.0, 133.1]),
        close=np.array([100.0, 110.0, 121.0, 133.1]),
        price_returns=np.array([0.1, 0.1, 0.1, 0.0]),
        funding_rates=np.zeros(4),
        ema={},
        atr={},
        rolling_high={},
        rolling_low={},
        rolling_mean={},
        rolling_std={},
    )

    returns, positions = strategy_returns(
        market,
        np.array([1.0, 1.0, 1.0, 1.0]),
        cost=0.0,
    )

    assert positions.tolist() == [0.0, 1.0, 1.0, 1.0]
    assert returns.tolist() == pytest.approx([0.0, 0.1, 0.1, 0.0])


def test_30m_monthly_breaker_reports_actual_flat_position() -> None:
    timestamps = pd.date_range("2026-01-01", periods=5, freq="30min", tz="UTC")
    market = Market(
        frame=pd.DataFrame(),
        timestamps=timestamps,
        open_=np.ones(5),
        high=np.ones(5),
        low=np.ones(5),
        close=np.ones(5),
        price_returns=np.array([0.0, -0.05, 0.10, 0.10, 0.0]),
        funding_rates=np.zeros(5),
        ema={},
        atr={},
        rolling_high={},
        rolling_low={},
        rolling_mean={},
        rolling_std={},
    )

    _, positions = strategy_returns(
        market,
        np.ones(5),
        cost=0.0,
        breaker_cap=0.04,
    )

    assert positions.tolist() == [0.0, 1.0, 0.0, 0.0, 0.0]


def test_asymmetric_window_groups_daily_and_monthly_returns() -> None:
    timestamps = pd.date_range("2026-01-31", periods=96, freq="30min", tz="UTC")
    window = Window.make(
        timestamps, timestamps[0], timestamps[-1] + pd.Timedelta(minutes=30)
    )
    net = np.zeros(96)
    net[1] = 0.01
    net[49] = 0.02
    positions = np.ones(96)

    metrics = window.metrics(net, positions)
    monthly = window.monthly(net)

    assert metrics.total_return == pytest.approx(1.01 * 1.02 - 1)
    assert metrics.green_months == 2
    assert [month for month, _ in monthly] == ["2026-01", "2026-02"]
    assert _group_starts(np.array([1, 1, 2, 2, 3])).tolist() == [0, 2, 4]


def test_30m_download_rejects_unsafe_filename_stem_before_network(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="filename_stem"):
        download_30m_dataset(tmp_path, years=6, filename_stem="../unsafe")


def test_asymmetric_candidate_filter_can_exclude_mean_reversion() -> None:
    selected = _selected_candidates(
        frozenset({"ema", "momentum", "donchian", "channel", "ensemble"})
    )

    assert selected
    assert "mean_reversion" not in {candidate.family for candidate in selected}


def test_intraday_download_rejects_unsupported_interval_before_network(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="interval"):
        download_intraday_dataset(
            tmp_path,
            years=6,
            interval="2h",  # type: ignore[arg-type]
            filename_stem="btcusdt_2h_6y",
        )
