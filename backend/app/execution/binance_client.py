"""Binance USDT-M Futures client (REST + signing).

Market-data endpoints (klines, exchangeInfo, time) are public. Signed endpoints
(account, orders) use HMAC-SHA256 and arrive in later stages. Same code path for
DEMO and LIVE — only the base URL and key pair differ (INTEGRATIONS.md).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import random
import time
import urllib.parse
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from app.core.logging import get_logger

_log = get_logger("binance")

# Base URLs per environment (verified 2026 — the old testnet host is retired).
BASE_URLS: dict[str, str] = {
    "DEMO": "https://demo-fapi.binance.com",
    "LIVE": "https://fapi.binance.com",
}
WS_URLS: dict[str, str] = {
    "DEMO": "wss://demo-fstream.binance.com",
    "LIVE": "wss://fstream.binance.com",
}


class BinanceError(Exception):
    """A Binance API error (carries HTTP status and Binance error code)."""

    def __init__(self, message: str, *, status: int | None = None, code: int | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class RateLimitError(BinanceError):
    """HTTP 429/418 — back off before retrying."""


@dataclass(frozen=True)
class Kline:
    """A single 4h candle from Binance (Decimal money, UTC ms open time)."""

    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    close_time_ms: int
    is_closed: bool

    @classmethod
    def from_rest(cls, row: list[Any]) -> Kline:
        """Parse a REST /klines row (always a closed candle)."""
        return cls(
            open_time_ms=int(row[0]),
            open=Decimal(str(row[1])),
            high=Decimal(str(row[2])),
            low=Decimal(str(row[3])),
            close=Decimal(str(row[4])),
            volume=Decimal(str(row[5])),
            close_time_ms=int(row[6]),
            is_closed=True,
        )


def sign_query(secret: str, params: dict[str, Any]) -> str:
    """Return the HMAC-SHA256 signature for a query-parameter mapping."""
    query = urllib.parse.urlencode(params)
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


class BinanceClient:
    """Async REST client with retry/backoff and optional HMAC signing."""

    def __init__(
        self,
        environment: str,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        client: httpx.AsyncClient | None = None,
        max_retries: int = 4,
        recv_window: int = 5000,
    ) -> None:
        if environment not in BASE_URLS:
            raise ValueError(f"unknown environment: {environment}")
        self.environment = environment
        self.base_url = BASE_URLS[environment]
        self.ws_url = WS_URLS[environment]
        self._api_key = api_key
        self._api_secret = api_secret
        self._client = client or httpx.AsyncClient(base_url=self.base_url, timeout=15.0)
        self._owns_client = client is None
        self._max_retries = max_retries
        self._recv_window = recv_window

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> BinanceClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    # --- Public market data ---

    async def get_server_time_ms(self) -> int:
        data = await self._request("GET", "/fapi/v1/time")
        return int(data["serverTime"])

    async def get_klines(self, symbol: str, interval: str, *, limit: int = 500) -> list[Kline]:
        """Fetch closed klines (most recent last). Public endpoint."""
        data = await self._request(
            "GET",
            "/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        return [Kline.from_rest(row) for row in data]

    async def get_exchange_filters(self, symbol: str) -> dict[str, Any]:
        """Return lot-size / min-notional filters for a symbol (public)."""
        data = await self._request("GET", "/fapi/v1/exchangeInfo")
        for sym in data.get("symbols", []):
            if sym.get("symbol") == symbol:
                return {f["filterType"]: f for f in sym.get("filters", [])}
        raise BinanceError(f"symbol {symbol} not found in exchangeInfo")

    async def clock_drift_ms(self) -> int:
        """Return local-minus-server clock drift in ms (for recvWindow safety)."""
        server = await self.get_server_time_ms()
        return int(time.time() * 1000) - server

    # --- Signed request (account/orders; used from Stage 4) ---

    async def signed_request(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        """Perform an HMAC-signed request. Requires api_key + api_secret."""
        if not self._api_key or not self._api_secret:
            raise BinanceError("signed request requires API credentials")
        p: dict[str, Any] = dict(params or {})
        p["timestamp"] = int(time.time() * 1000)
        p["recvWindow"] = self._recv_window
        p["signature"] = sign_query(self._api_secret, p)
        return await self._request(method, path, params=p, signed=True)

    # --- Core request with retry/backoff ---

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        headers = {"X-MBX-APIKEY": self._api_key} if signed and self._api_key else {}
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                resp = await self._client.request(
                    method, path, params=params, headers=headers
                )
                if resp.status_code in (418, 429):
                    raise RateLimitError(
                        f"rate limited ({resp.status_code})", status=resp.status_code
                    )
                if resp.status_code >= 400:
                    self._raise_api_error(resp)
                return resp.json()
            except RateLimitError as exc:
                last_exc = exc
                # Honour Retry-After when present, else exponential backoff (never tight-loop).
                delay = self._backoff(attempt, base=1.0)
                _log.warning("binance_rate_limited", attempt=attempt, delay=round(delay, 2))
                await asyncio.sleep(delay)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                _log.warning("binance_transport_error", attempt=attempt, error=str(exc))
                await asyncio.sleep(self._backoff(attempt))
        raise BinanceError(f"request failed after {self._max_retries} attempts: {last_exc}")

    @staticmethod
    def _backoff(attempt: int, *, base: float = 0.5, cap: float = 8.0) -> float:
        """Exponential backoff with full jitter."""
        return random.uniform(0, min(cap, base * (2**attempt)))

    @staticmethod
    def _raise_api_error(resp: httpx.Response) -> None:
        code: int | None = None
        message = resp.text
        try:
            body = resp.json()
            code = body.get("code")
            message = body.get("msg", message)
        except ValueError:
            pass
        raise BinanceError(message, status=resp.status_code, code=code)
