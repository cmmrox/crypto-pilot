"""Validate and inspect the installed strategy plugin catalog."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from app.strategies import default_strategy, registered_strategies


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "list"), nargs="?", default="validate")
    args = parser.parse_args()
    strategies = registered_strategies()
    if args.command == "list":
        print(
            json.dumps(
                [asdict(strategy.manifest) for strategy in strategies],
                indent=2,
                default=str,
            )
        )
    else:
        default = default_strategy().manifest.strategy_id
        print(f"validated {len(strategies)} strategy plugins; default={default}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
