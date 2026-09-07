"""Result serialization and human-readable report generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

from trend_rider_lab.binance_data import sha256
from trend_rider_lab.replay import ReplayResult, config_dict


def result_summary(result: ReplayResult) -> dict[str, object]:
    trades = result.trades
    closed = len(trades)
    net_values = (
        [Decimal(str(value)) for value in trades["net_pnl"].tolist()] if closed else []
    )
    wins = sum(value > 0 for value in net_values)
    gross_profit = (
        sum((value for value in net_values if value > 0), Decimal("0"))
        if closed
        else Decimal("0")
    )
    gross_loss = (
        -sum((value for value in net_values if value < 0), Decimal("0"))
        if closed
        else Decimal("0")
    )
    fees = (
        sum(
            (Decimal(str(value)) for value in trades["fees"].tolist()),
            Decimal("0"),
        )
        if closed
        else Decimal("0")
    )
    funding = (
        sum(
            (Decimal(str(value)) for value in trades["funding"].tolist()),
            Decimal("0"),
        )
        if closed
        else Decimal("0")
    )
    monthly = (
        [float(value) for value in result.monthly["return"].tolist()]
        if not result.monthly.empty
        else []
    )
    return {
        "period_start": result.start.isoformat(),
        "period_end": result.end.isoformat(),
        "latest_close": str(result.latest_close),
        "initial_capital": str(result.config.initial_capital),
        "final_equity": str(result.final_equity),
        "profit": str(result.profit),
        "total_return": str(result.total_return),
        "cagr": str(result.cagr),
        "max_drawdown": str(result.max_drawdown),
        "sharpe": str(result.sharpe),
        "closed_trades": closed,
        "winning_trades": wins,
        "win_rate": str(Decimal(wins) / Decimal(closed)) if closed else "0",
        "profit_factor": str(gross_profit / gross_loss) if gross_loss > 0 else None,
        "fees": str(fees),
        "funding": str(funding),
        "green_months": sum(value > 0 for value in monthly),
        "red_months": sum(value < 0 for value in monthly),
        "flat_months": sum(value == 0 for value in monthly),
        "best_month": str(float(max(monthly))) if len(monthly) else None,
        "worst_month": str(float(min(monthly))) if len(monthly) else None,
        "open_position": result.open_position,
        "skipped_long_entries": result.skipped_long_entries,
        "skipped_short_entries": result.skipped_short_entries,
        "long_breaker_trips": result.long_breaker_trips,
        "short_breaker_trips": result.short_breaker_trips,
        "funding_events_applied": result.funding_events_applied,
        "funding_mark_fallbacks": result.funding_mark_fallbacks,
        "period_bars": result.period_bars,
        "config": config_dict(result.config),
    }


def write_run(
    result: ReplayResult,
    *,
    results_root: Path,
    candles_path: Path,
    funding_path: Path,
    filters_path: Path,
    source_commit: str,
    server_time_ms: int,
) -> Path:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = results_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    result.equity.to_csv(run_dir / "equity.csv", index=False)
    result.trades.to_csv(run_dir / "trades.csv", index=False)
    result.monthly.to_csv(run_dir / "monthly.csv", index=False)
    summary = result_summary(result)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_commit": source_commit,
        "binance_server_time_ms": server_time_ms,
        "inputs": {
            str(candles_path): sha256(candles_path),
            str(funding_path): sha256(funding_path),
            str(filters_path): sha256(filters_path),
        },
        "lab_sources": {
            str(path): sha256(path)
            for path in sorted(
                (results_root.parent / "src" / "trend_rider_lab").glob("*.py")
            )
        },
        "assumptions": [
            "closed Binance USD-M BTCUSDT 4h candles only",
            "200 pre-period warmup bars; account starts flat at period boundary",
            "signals at close, fills at next open",
            "production strategy indicators/constants and Decimal sizing/filter code",
            "long 0.04% per fill; short 0.05% per fill",
            "actual public funding rates applied to carried positions",
            "bar open proxies notional when Binance funding history omits markPrice",
            "current public exchange filters applied to historical replay",
            (
                "independent 4% monthly breakers flatten next open"
                if result.config.monthly_breakers_enabled
                else "both monthly breakers disabled for controlled comparison"
            ),
            "OHLC replay is not tick/order-book or liquidation-engine simulation",
        ],
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (run_dir / "report.md").write_text(_markdown_report(summary), encoding="utf-8")
    return run_dir


def _pct(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{Decimal(str(value)) * Decimal('100'):.2f}%"


def _markdown_report(summary: dict[str, object]) -> str:
    config = cast("dict[str, object]", summary["config"])
    breakers_enabled = bool(config["monthly_breakers_enabled"])
    breaker_label = (
        "with monthly breakers" if breakers_enabled else "without monthly breakers"
    )
    return f"""# Trend Rider v6 replay — {breaker_label}

Generated over public Binance USD-M BTCUSDT 4h data.

## Headline

- Period: {summary["period_start"]} to {summary["period_end"]}
- Closed 4h bars replayed: {summary["period_bars"]}
- Initial capital: ${Decimal(str(summary["initial_capital"])):.2f}
- Final marked equity: ${Decimal(str(summary["final_equity"])):.2f}
- Historical profit/loss: ${Decimal(str(summary["profit"])):.2f}
- Total return: {_pct(summary["total_return"])}
- CAGR: {_pct(summary["cagr"])}
- Maximum drawdown: {_pct(summary["max_drawdown"])}
- Sharpe: {Decimal(str(summary["sharpe"])):.2f}
- Monthly breakers: {"enabled" if breakers_enabled else "disabled"}

## Trading

- Closed trades: {summary["closed_trades"]}
- Win rate: {_pct(summary["win_rate"])}
- Profit factor: {summary["profit_factor"] or "n/a"}
- Fees: ${Decimal(str(summary["fees"])):.2f}
- Net funding: ${Decimal(str(summary["funding"])):.2f}
- Funding events applied / missing-mark fallbacks:
  {summary["funding_events_applied"]}/{summary["funding_mark_fallbacks"]}
- Months green/red/flat: {summary["green_months"]}/{summary["red_months"]}/{summary["flat_months"]}
- Best/worst month: {_pct(summary["best_month"])} / {_pct(summary["worst_month"])}
- Long/short breaker trips: {summary["long_breaker_trips"]}/{summary["short_breaker_trips"]}
- Entries skipped by current exchange minimums, long/short:
  {summary["skipped_long_entries"]}/{summary["skipped_short_entries"]}
- Open position at end: {summary["open_position"] or "none"}

## Interpretation boundary

This is historical evidence for the configured algorithm under explicit OHLC
execution assumptions. It is not a forecast, guaranteed return, tick-level fill
simulation, or proof that the live bot currently wires every validated intent and
breaker path. Review the separate live-path audit before treating this as deployable
behavior.
"""
