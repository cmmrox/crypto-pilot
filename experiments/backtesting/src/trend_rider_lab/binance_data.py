"""Public Binance USD-M market-data download with bounded retries.

No credential is read or sent. The downloader follows the official public
``/fapi/v1/klines``, ``/fapi/v1/fundingRate``, ``/fapi/v1/exchangeInfo`` and
``/fapi/v1/time`` contracts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeAlias

import httpx
from app.execution.filters import SymbolFilters

BASE_URL = "https://fapi.binance.com"
FOUR_HOURS_MS = 4 * 60 * 60 * 1000
KLINE_LIMIT = 1500
FUNDING_LIMIT = 1000
QueryValue: TypeAlias = str | int | float | bool | None
KlineRow: TypeAlias = list[Any]
FundingRow: TypeAlias = dict[str, Any]


@dataclass(frozen=True)
class DownloadedData:
    candles_path: Path
    funding_path: Path
    filters_path: Path
    server_time_ms: int
    latest_closed_open_ms: int


class PublicBinanceClient:
    """Small synchronous client with retry/backoff for public data only."""

    def __init__(self, base_url: str = BASE_URL) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=30.0, headers={"User-Agent": "CryptoPilotLab/1.0"})

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, params: dict[str, QueryValue] | None = None) -> Any:
        delay = 1.0
        last_error: BaseException | None = None
        for attempt in range(5):
            try:
                response = self._client.get(f"{self._base_url}{path}", params=params)
                if response.status_code in {418, 429}:
                    retry_after = float(response.headers.get("Retry-After", delay))
                    time.sleep(min(max(retry_after, delay), 30.0))
                    delay = min(delay * 2, 30.0)
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt == 4:
                    break
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
        raise RuntimeError(f"public Binance request failed: {path}") from last_error

    def server_time_ms(self) -> int:
        payload = self._get("/fapi/v1/time")
        return int(payload["serverTime"])

    def exchange_filters(self, symbol: str) -> tuple[SymbolFilters, dict[str, object]]:
        payload = self._get("/fapi/v1/exchangeInfo")
        row = next(item for item in payload["symbols"] if item["symbol"] == symbol)
        by_type = {item["filterType"]: item for item in row["filters"]}
        filters = SymbolFilters.from_exchange(by_type)
        public = {
            "symbol": symbol,
            "status": row["status"],
            "contract_type": row["contractType"],
            "step_size": str(filters.step_size),
            "min_qty": str(filters.min_qty),
            "max_qty": str(filters.max_qty),
            "tick_size": str(filters.tick_size),
            "min_notional": str(filters.min_notional),
        }
        return filters, public

    def klines(
        self,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        server_time_ms: int,
    ) -> list[KlineRow]:
        rows: list[KlineRow] = []
        cursor = start_ms
        while cursor <= end_ms:
            batch = self._get(
                "/fapi/v1/klines",
                {
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": cursor,
                    "endTime": end_ms,
                    "limit": KLINE_LIMIT,
                },
            )
            if not batch:
                break
            rows.extend(row for row in batch if int(row[6]) < server_time_ms)
            next_cursor = int(batch[-1][0]) + FOUR_HOURS_MS
            if next_cursor <= cursor:
                raise RuntimeError("Binance kline pagination did not advance")
            cursor = next_cursor
            if len(batch) < KLINE_LIMIT:
                break
        unique = {int(row[0]): row for row in rows}
        return [unique[key] for key in sorted(unique)]

    def funding(self, symbol: str, start_ms: int, end_ms: int) -> list[FundingRow]:
        rows: list[FundingRow] = []
        cursor = start_ms
        while cursor <= end_ms:
            batch = self._get(
                "/fapi/v1/fundingRate",
                {
                    "symbol": symbol,
                    "startTime": cursor,
                    "endTime": end_ms,
                    "limit": FUNDING_LIMIT,
                },
            )
            if not batch:
                break
            rows.extend(batch)
            next_cursor = int(batch[-1]["fundingTime"]) + 1
            if next_cursor <= cursor:
                raise RuntimeError("Binance funding pagination did not advance")
            cursor = next_cursor
            if len(batch) < FUNDING_LIMIT:
                break
        unique = {int(row["fundingTime"]): row for row in rows}
        return [unique[key] for key in sorted(unique)]


def latest_closed_open_ms(server_time_ms: int) -> int:
    """Open time of the newest 4h candle that has fully closed."""
    current_open = (server_time_ms // FOUR_HOURS_MS) * FOUR_HOURS_MS
    return current_open - FOUR_HOURS_MS


def download_dataset(
    data_dir: Path,
    *,
    symbol: str,
    warmup_start_ms: int,
    latest_open_ms: int,
) -> DownloadedData:
    data_dir.mkdir(parents=True, exist_ok=True)
    client = PublicBinanceClient()
    try:
        server_time = client.server_time_ms()
        filters, public_filters = client.exchange_filters(symbol)
        del filters
        candles = client.klines(
            symbol,
            "4h",
            warmup_start_ms,
            latest_open_ms,
            server_time,
        )
        funding = client.funding(symbol, warmup_start_ms, server_time)
    finally:
        client.close()
    if not candles:
        raise RuntimeError("Binance returned no closed candles for the requested period")

    candles_path = data_dir / "btcusdt_4h.csv"
    funding_path = data_dir / "btcusdt_funding.csv"
    filters_path = data_dir / "btcusdt_filters.json"
    _write_candles(candles_path, candles)
    _write_funding(funding_path, funding)
    filters_path.write_text(json.dumps(public_filters, indent=2) + "\n", encoding="utf-8")
    return DownloadedData(
        candles_path=candles_path,
        funding_path=funding_path,
        filters_path=filters_path,
        server_time_ms=server_time,
        latest_closed_open_ms=int(candles[-1][0]),
    )


def _write_candles(path: Path, rows: list[KlineRow]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "open_time_ms",
                "dt",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time_ms",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    int(row[0]),
                    datetime.fromtimestamp(int(row[0]) / 1000, UTC).isoformat(),
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    int(row[6]),
                ]
            )


def _write_funding(path: Path, rows: list[FundingRow]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["funding_time_ms", "dt", "funding_rate", "mark_price"])
        for row in rows:
            timestamp = int(row["fundingTime"])
            writer.writerow(
                [
                    timestamp,
                    datetime.fromtimestamp(timestamp / 1000, UTC).isoformat(),
                    row["fundingRate"],
                    row["markPrice"],
                ]
            )


def load_filters(path: Path) -> SymbolFilters:
    row = json.loads(path.read_text(encoding="utf-8"))
    return SymbolFilters(
        step_size=Decimal(row["step_size"]),
        min_qty=Decimal(row["min_qty"]),
        max_qty=Decimal(row["max_qty"]),
        tick_size=Decimal(row["tick_size"]),
        min_notional=Decimal(row["min_notional"]),
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
