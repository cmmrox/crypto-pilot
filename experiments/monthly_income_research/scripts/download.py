"""Download public Binance market data for the monthly-income research.

Only public, unauthenticated endpoints are used. No account credential is read.
Candles are closed bars only (close time before server time).
"""

from __future__ import annotations

import argparse
import csv
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

FAPI = "https://fapi.binance.com"
SPOT = "https://api.binance.com"
DATA = Path(__file__).resolve().parents[1] / "data"
INTERVAL_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def _get(client: httpx.Client, url: str, params: dict[str, object]) -> object:
    delay = 1.0
    for attempt in range(6):
        try:
            response = client.get(url, params=params)
            if response.status_code in {418, 429}:
                time.sleep(min(float(response.headers.get("Retry-After", delay)), 60.0))
                delay *= 2
                continue
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            if attempt == 5:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(url)


def klines(market: str, symbol: str, interval: str, start: datetime) -> Path:
    base, path, limit = (
        (FAPI, "/fapi/v1/klines", 1500) if market == "perp" else (SPOT, "/api/v3/klines", 1000)
    )
    step = INTERVAL_MS[interval]
    out = DATA / f"{symbol.lower()}_{market}_{interval}.csv"
    with httpx.Client(timeout=30.0, headers={"User-Agent": "CryptoPilotResearch/1.0"}) as client:
        server = int(_get(client, f"{FAPI}/fapi/v1/time", {})["serverTime"])  # type: ignore[index]
        cursor = int(start.timestamp() * 1000)
        rows: dict[int, list[object]] = {}
        while cursor < server:
            batch = _get(
                client,
                f"{base}{path}",
                {"symbol": symbol, "interval": interval, "startTime": cursor, "limit": limit},
            )
            assert isinstance(batch, list)
            if not batch:
                break
            for row in batch:
                if int(row[6]) < server:  # closed bars only
                    rows[int(row[0])] = row
            nxt = int(batch[-1][0]) + step
            if nxt <= cursor:
                raise RuntimeError("pagination stalled")
            cursor = nxt
            if len(batch) < limit:
                break
    with out.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["open_time_ms", "dt", "open", "high", "low", "close", "volume",
                         "quote_volume", "trades", "taker_buy_base"])
        for key in sorted(rows):
            r = rows[key]
            writer.writerow([key, datetime.fromtimestamp(key / 1000, UTC).isoformat(),
                             r[1], r[2], r[3], r[4], r[5], r[7], r[8], r[9]])
    print(f"{out.name}: {len(rows)} closed bars, "
          f"{datetime.fromtimestamp(min(rows) / 1000, UTC)} -> "
          f"{datetime.fromtimestamp(max(rows) / 1000, UTC)}")
    return out


def funding(symbol: str, start: datetime) -> Path:
    out = DATA / f"{symbol.lower()}_funding.csv"
    with httpx.Client(timeout=30.0, headers={"User-Agent": "CryptoPilotResearch/1.0"}) as client:
        cursor = int(start.timestamp() * 1000)
        rows: dict[int, dict[str, object]] = {}
        while True:
            batch = _get(client, f"{FAPI}/fapi/v1/fundingRate",
                         {"symbol": symbol, "startTime": cursor, "limit": 1000})
            assert isinstance(batch, list)
            if not batch:
                break
            for row in batch:
                rows[int(row["fundingTime"])] = row
            nxt = int(batch[-1]["fundingTime"]) + 1
            if nxt <= cursor:
                break
            cursor = nxt
            if len(batch) < 1000:
                break
    with out.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["funding_time_ms", "dt", "funding_rate", "mark_price"])
        for key in sorted(rows):
            r = rows[key]
            writer.writerow([key, datetime.fromtimestamp(key / 1000, UTC).isoformat(),
                             r["fundingRate"], r.get("markPrice", "")])
    print(f"{out.name}: {len(rows)} funding events")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="BTCUSDT")
    parser.add_argument("--intervals", default="1h,4h,1d")
    parser.add_argument("--start", default="2019-09-08")
    parser.add_argument("--spot", action="store_true")
    parser.add_argument("--no-funding", action="store_true")
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    start = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    for symbol in args.symbols.split(","):
        for interval in args.intervals.split(","):
            klines("perp", symbol, interval, start)
            if args.spot:
                klines("spot", symbol, interval, start)
        if not args.no_funding:
            funding(symbol, start)


if __name__ == "__main__":
    main()
