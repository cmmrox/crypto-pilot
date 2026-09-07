"""Explicit, immutable reconciliation of conflicting native candles from 1m evidence."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any

import pandas as pd
from strategy_runtime.parameters import INTERVAL_MINUTES

from experiment_lab.adapters.binance import validate_dataset


def aggregate_minutes(raw: list[list[Any]], interval: str) -> pd.DataFrame:
    # Binance raw kline records mix timestamps, string prices and counts.
    frame = pd.DataFrame(
        [
            {
                "dt": pd.Timestamp(row[0], unit="ms", tz="UTC"),
                **{
                    key: Decimal(value)
                    for key, value in zip(
                        ("open", "high", "low", "close", "volume"),
                        row[1:6],
                        strict=True,
                    )
                },
            }
            for row in raw
        ]
    ).set_index("dt")
    step = INTERVAL_MINUTES[interval]
    if (
        frame.empty
        or not (
            frame.index.to_series().diff().dropna() == pd.Timedelta(minutes=1)
        ).all()
    ):
        raise ValueError("Minute source has gaps or duplicates")
    groups = frame.resample(pd.Timedelta(minutes=step))
    if not (groups.size() == step).all():
        raise ValueError("Incomplete minute group cannot replace a native candle")
    return groups.agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )


def reconcile(
    original: dict[str, Any], original_id: str, minutes: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    result = deepcopy(original)
    index = {row["dt"]: i for i, row in enumerate(result["candles"])}
    patches = []
    for digest, source in minutes.items():
        if source["interval"] != "1m" or source["endpoint"] != "/fapi/v1/klines":
            raise ValueError("Expected archived Binance 1m response")
        for timestamp, row in aggregate_minutes(
            source["raw"], original["interval"]
        ).iterrows():
            key = pd.Timestamp(str(timestamp)).isoformat()
            replacement = {"dt": key, **{k: str(v) for k, v in row.items()}}
            previous = result["candles"][index[key]]
            if any(
                Decimal(previous[k]) != Decimal(replacement[k])
                for k in ("open", "high", "low", "close", "volume")
            ):
                patches.append(
                    {
                        "dt": key,
                        "original": previous,
                        "replacement": replacement,
                        "minute_artifact": digest,
                    }
                )
            result["candles"][index[key]] = replacement
    result["reconciliation"] = {
        "original_dataset": original_id,
        "minute_sources": list(minutes),
        "changed_bars": patches,
        "method": "Replace conflicting windows with complete aggregates of actual Binance 1m candles; originals retained. Not raw-trade verification.",
    }
    validate_dataset(result)
    return result
