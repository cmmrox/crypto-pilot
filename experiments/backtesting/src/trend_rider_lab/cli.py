"""Command-line entry point for the isolated Trend Rider v6 backtesting lab."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from trend_rider_lab.binance_data import (
    FOUR_HOURS_MS,
    DownloadedData,
    PublicBinanceClient,
    download_dataset,
    latest_closed_open_ms,
    load_filters,
)
from trend_rider_lab.live_path_audit import audit
from trend_rider_lab.replay import ReplayConfig, run_replay
from trend_rider_lab.reporting import result_summary, write_run

REPO_ROOT = Path(__file__).resolve().parents[4]
LAB_ROOT = REPO_ROOT / "experiments" / "backtesting"
DATA_DIR = LAB_ROOT / "data" / "raw"
RESULTS_DIR = LAB_ROOT / "results"
WARMUP_BARS = 200


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CryptoPilot Trend Rider v6 backtesting lab")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="download/reuse public data and run a chronological replay")
    run.add_argument("--years", type=int, default=3)
    run.add_argument("--initial-capital", type=Decimal, default=Decimal("100"))
    run.add_argument("--reuse-data", action="store_true")
    run.add_argument("--no-funding", action="store_true")
    run.add_argument(
        "--filters-path",
        type=Path,
        help="override the exchange-filter snapshot (for example current DEMO filters)",
    )
    sub.add_parser("audit-live-path", help="check live bot coverage of validated intents/breakers")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "audit-live-path":
        result = audit(REPO_ROOT)
        print(json.dumps(result.__dict__, indent=2))
        return 0 if result.passed else 2
    return _run(args)


def _run(args: argparse.Namespace) -> int:
    if args.years <= 0:
        raise SystemExit("--years must be positive")
    dataset = _prepare_data(args.reuse_data, args.years)
    filters_path = args.filters_path.resolve() if args.filters_path else dataset.filters_path
    if not filters_path.is_file():
        raise SystemExit(f"missing filters file: {filters_path}")
    latest_open = pd.Timestamp(dataset.latest_closed_open_ms, unit="ms", tz="UTC")
    start = latest_open.replace(year=latest_open.year - args.years)
    candles = pd.read_csv(dataset.candles_path)
    funding = pd.read_csv(dataset.funding_path)
    config = ReplayConfig(
        initial_capital=args.initial_capital,
        funding_enabled=not args.no_funding,
    )
    result = run_replay(
        candles,
        funding,
        load_filters(filters_path),
        config,
        start=start,
    )
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    run_dir = write_run(
        result,
        results_root=RESULTS_DIR,
        candles_path=dataset.candles_path,
        funding_path=dataset.funding_path,
        filters_path=filters_path,
        source_commit=source_commit,
        server_time_ms=dataset.server_time_ms,
    )
    print(json.dumps(result_summary(result), indent=2, sort_keys=True))
    print(f"results_dir={run_dir}")
    return 0


def _prepare_data(reuse_data: bool, years: int) -> DownloadedData:
    candles_path = DATA_DIR / "btcusdt_4h.csv"
    funding_path = DATA_DIR / "btcusdt_funding.csv"
    filters_path = DATA_DIR / "btcusdt_filters.json"
    if reuse_data:
        for path in (candles_path, funding_path, filters_path):
            if not path.exists():
                raise SystemExit(f"--reuse-data requested but missing {path}")
        client = PublicBinanceClient()
        try:
            server_time = client.server_time_ms()
        finally:
            client.close()
        candles = pd.read_csv(candles_path)
        latest_open = int(candles["open_time_ms"].max())
        return DownloadedData(
            candles_path=candles_path,
            funding_path=funding_path,
            filters_path=filters_path,
            server_time_ms=server_time,
            latest_closed_open_ms=latest_open,
        )

    client = PublicBinanceClient()
    try:
        server_time = client.server_time_ms()
    finally:
        client.close()
    latest_open = latest_closed_open_ms(server_time)
    latest_dt = datetime.fromtimestamp(latest_open / 1000, UTC)
    start_dt = latest_dt.replace(year=latest_dt.year - years)
    warmup_start_ms = int(start_dt.timestamp() * 1000) - WARMUP_BARS * FOUR_HOURS_MS
    return download_dataset(
        DATA_DIR,
        symbol="BTCUSDT",
        warmup_start_ms=warmup_start_ms,
        latest_open_ms=latest_open,
    )


if __name__ == "__main__":
    raise SystemExit(main())
