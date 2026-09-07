"""Operator data preparation; does not start studies or alter the live application."""

import argparse
from datetime import datetime

from experiment_lab.adapters.artifacts import Artifacts
from experiment_lab.adapters.binance import BinanceData
from experiment_lab.settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start",
        required=True,
        help="UTC-aware inclusive start, e.g. 2023-09-01T00:00:00Z",
    )
    parser.add_argument("--end", required=True, help="UTC-aware exclusive end")
    parser.add_argument("--interval", choices=["4h", "1h", "30m"], default="4h")
    args = parser.parse_args()
    settings = Settings()
    dataset = BinanceData(Artifacts(settings.data_dir / "artifacts")).download(
        datetime.fromisoformat(args.start),
        datetime.fromisoformat(args.end),
        args.interval,
    )
    print(f"Verified dataset ID: {dataset}")


if __name__ == "__main__":
    main()
