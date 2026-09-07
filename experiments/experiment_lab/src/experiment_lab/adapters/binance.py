"""Public USD-M dataset acquisition. No credentials and no trading endpoints."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pandas as pd
from strategy_runtime.filters import SymbolFilters
from strategy_runtime.parameters import INTERVAL_MINUTES

from experiment_lab.adapters.artifacts import Artifacts

API = "https://fapi.binance.com"
ARCHIVE = "https://data.binance.vision/data/futures/um"


class BinanceData:
    def __init__(self, artifacts: Artifacts):
        self.artifacts = artifacts

    @staticmethod
    def get(
        client: httpx.Client, url: str, params: dict | None = None
    ) -> httpx.Response:
        for attempt in range(4):
            response = client.get(url, params=params)
            if response.status_code not in (418, 429, 500, 502, 503, 504):
                response.raise_for_status()
                return response
            if attempt < 3:
                time.sleep(
                    min(
                        30,
                        max(1, float(response.headers.get("Retry-After", 2**attempt))),
                    )
                )
        response.raise_for_status()
        raise RuntimeError("Binance unavailable")

    def download(self, start: datetime, end: datetime, interval: str) -> str:
        """Download completed candles including maximum supported warmup; end exclusive."""
        step = INTERVAL_MINUTES[interval] * 60_000
        start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
        if (
            start.tzinfo is None
            or end.tzinfo is None
            or start_ms % step
            or end_ms % step
        ):
            raise ValueError(
                "Dates must be timezone-aware and aligned to interval boundaries"
            )
        if end_ms <= start_ms or end_ms - start_ms > 4 * 366 * 86400000:
            raise ValueError(
                "Dataset window must be positive and no longer than four years"
            )
        sources = []
        candles = []
        funding = []
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            server_ms = self.get(client, f"{API}/fapi/v1/time").json()["serverTime"]
            if end_ms > server_ms // step * step:
                raise ValueError("Dataset includes an unclosed candle")
            cursor = start_ms - 400 * step
            while cursor < end_ms:
                response = self.get(
                    client,
                    f"{API}/fapi/v1/klines",
                    {
                        "symbol": "BTCUSDT",
                        "interval": interval,
                        "startTime": cursor,
                        "endTime": end_ms - 1,
                        "limit": 1500,
                    },
                )
                sources.append(
                    {
                        "endpoint": "/fapi/v1/klines",
                        "start_ms": cursor,
                        "sha256": hashlib.sha256(response.content).hexdigest(),
                    }
                )
                batch = response.json()
                if not batch or int(batch[0][0]) != cursor:
                    raise ValueError("Binance candle coverage is incomplete")
                for row in batch:
                    if int(row[6]) >= server_ms:
                        raise ValueError("Unclosed Binance candle")
                    candles.append(
                        {
                            "dt": pd.Timestamp(
                                int(row[0]), unit="ms", tz="UTC"
                            ).isoformat(),
                            **dict(
                                zip(
                                    ("open", "high", "low", "close", "volume"),
                                    map(str, row[1:6]),
                                    strict=True,
                                )
                            ),
                        }
                    )
                next_cursor = int(batch[-1][0]) + step
                if next_cursor <= cursor:
                    raise ValueError("Candle pagination did not advance")
                cursor = next_cursor
            cursor = start_ms
            while cursor < end_ms:
                response = self.get(
                    client,
                    f"{API}/fapi/v1/fundingRate",
                    {
                        "symbol": "BTCUSDT",
                        "startTime": cursor,
                        "endTime": end_ms - 1,
                        "limit": 1000,
                    },
                )
                sources.append(
                    {
                        "endpoint": "/fapi/v1/fundingRate",
                        "start_ms": cursor,
                        "sha256": hashlib.sha256(response.content).hexdigest(),
                    }
                )
                batch = response.json()
                if not batch:
                    break
                for row in batch:
                    funding.append(
                        {
                            "dt": pd.Timestamp(
                                row["fundingTime"], unit="ms", tz="UTC"
                            ).isoformat(),
                            "funding_rate": row["fundingRate"],
                            "mark_price": row["markPrice"],
                        }
                    )
                next_cursor = int(batch[-1]["fundingTime"]) + 1
                if next_cursor <= cursor:
                    raise ValueError("Funding pagination did not advance")
                cursor = next_cursor
            response = self.get(client, f"{API}/fapi/v1/exchangeInfo")
            symbol = next(
                row for row in response.json()["symbols"] if row["symbol"] == "BTCUSDT"
            )
            filters = SymbolFilters.from_exchange(
                {row["filterType"]: row for row in symbol["filters"]}
            )
        manifest = {
            "schema_version": 1,
            "source": "BINANCE_USDM_PUBLIC",
            "symbol": "BTCUSDT",
            "interval": interval,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "sources": sources,
            "candles": candles,
            "funding": funding,
            "filters": {key: str(value) for key, value in vars(filters).items()},
            "filter_assumption": "Current exchange filters applied historically",
            "fidelity": "CANDLE_REPLAY",
        }
        validate_dataset(manifest)
        return self.artifacts.put(manifest)


def validate_dataset(data: dict) -> None:
    if data.get("source") != "BINANCE_USDM_PUBLIC" or data.get("symbol") != "BTCUSDT":
        raise ValueError("Only Binance USD-M BTCUSDT datasets are supported")
    step = pd.Timedelta(minutes=INTERVAL_MINUTES[data["interval"]])
    frame = pd.DataFrame(data["candles"])
    times = pd.to_datetime(frame["dt"], utc=True)
    if len(frame) < 401 or not (times.diff().dropna() == step).all():
        raise ValueError("Candle coverage is incomplete or duplicated")
    if times.iloc[0] > pd.Timestamp(data["start"]) - 400 * step or times.iloc[
        -1
    ] + step != pd.Timestamp(data["end"]):
        raise ValueError("Dataset does not cover its declared window")
    for row in data["candles"]:
        opening, high, low, close, volume = (
            Decimal(row[key]) for key in ("open", "high", "low", "close", "volume")
        )
        if (
            not all(x.is_finite() for x in (opening, high, low, close, volume))
            or min(opening, high, low, close) <= 0
            or volume < 0
            or not low <= min(opening, close) <= max(opening, close) <= high
        ):
            raise ValueError("Invalid Binance OHLCV values")
    funding = sorted(pd.Timestamp(row["dt"]) for row in data["funding"])
    # Do not invent missing historical funding or silently disable it.
    if not funding or len(set(funding)) != len(funding):
        raise ValueError("Missing or duplicate funding history")
    boundaries = [pd.Timestamp(data["start"]), *funding, pd.Timestamp(data["end"])]
    if any(
        b - a > pd.Timedelta(hours=8, seconds=60)
        for a, b in zip(boundaries, boundaries[1:])
    ):
        raise ValueError("Funding history has a coverage gap")
