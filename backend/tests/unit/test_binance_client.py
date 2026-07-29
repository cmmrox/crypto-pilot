"""Unit tests for Binance client signing and kline parsing (QA-2)."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from app.execution.binance_client import (
    AmbiguousMutationError,
    BinanceClient,
    BinanceError,
    Kline,
    sign_query,
)


def test_sign_query_matches_binance_reference_vector() -> None:
    """HMAC-SHA256 must match Binance's published example exactly."""
    secret = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0"
    params = {
        "symbol": "LTCBTC",
        "side": "BUY",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": 1,
        "price": "0.1",
        "recvWindow": 5000,
        "timestamp": 1499827319559,
    }
    # Canonical HMAC-SHA256 of the exact query string, verified independently
    # with `openssl dgst -sha256 -hmac`.
    assert (
        sign_query(secret, params)
        == "b89008e7051ffbf2242be7dc5ae67fd146e6430688627b802c0cbec146e46aef"
    )


def test_kline_from_rest_uses_decimal() -> None:
    row = [
        1784318400000,
        "64126.00",
        "64148.70",
        "63860.80",
        "63925.80",
        "187511.6673",
        1784332799999,
        "12004090879.87",
        63325,
        "62754.59",
        "4017541609.00",
        "0",
    ]
    k = Kline.from_rest(row)
    assert k.open == Decimal("64126.00")
    assert k.close == Decimal("63925.80")
    assert isinstance(k.high, Decimal)
    assert k.is_closed
    assert k.open_time_ms == 1784318400000


def test_kline_from_rest_marks_still_forming_row_open() -> None:
    row = [
        2000,
        "1",
        "2",
        "0.5",
        "1.5",
        "10",
        5999,
        "0",
        1,
        "0",
        "0",
        "0",
    ]
    assert not Kline.from_rest(row, now_ms=5000).is_closed
    assert Kline.from_rest(row, now_ms=6000).is_closed


def test_unknown_environment_rejected() -> None:
    with pytest.raises(ValueError, match="unknown environment"):
        BinanceClient("STAGING")


def test_backoff_is_bounded_and_jittered() -> None:
    for attempt in range(6):
        for _ in range(20):
            d = BinanceClient._backoff(attempt)
            assert 0 <= d <= 8.0


@pytest.mark.asyncio
async def test_signed_request_requires_credentials() -> None:
    async with BinanceClient("DEMO") as client:
        with pytest.raises(BinanceError, match="requires API credentials"):
            await client.signed_request("GET", "/fapi/v2/balance")


@pytest.mark.asyncio
async def test_public_mark_price_and_ticker_are_parsed_as_decimal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/premiumIndex"):
            return httpx.Response(
                200,
                json={
                    "symbol": "BTCUSDT",
                    "markPrice": "117742.84233695",
                    "time": 1784450809123,
                },
            )
        return httpx.Response(
            200,
            json={"symbol": "BTCUSDT", "priceChangePercent": "1.27"},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.invalid",
    ) as raw:
        client = BinanceClient("DEMO", client=raw)
        mark = await client.get_mark_price("BTCUSDT")
        ticker = await client.get_ticker_24h("BTCUSDT")

    assert mark.price == Decimal("117742.84233695")
    assert mark.observed_at_ms == 1784450809123
    assert ticker.price_change_percent == Decimal("1.27")


@pytest.mark.asyncio
async def test_public_market_response_rejects_missing_required_fields() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"symbol": "BTCUSDT"})
        ),
        base_url="https://example.invalid",
    ) as raw:
        client = BinanceClient("DEMO", client=raw)
        with pytest.raises(BinanceError, match="missing positive price/time"):
            await client.get_mark_price("BTCUSDT")
        with pytest.raises(BinanceError, match="missing priceChangePercent"):
            await client.get_ticker_24h("BTCUSDT")


@pytest.mark.asyncio
async def test_signed_mutation_transport_failure_is_not_blindly_retried() -> None:
    attempts = 0

    def fail(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("connection dropped", request=request)

    transport = httpx.MockTransport(fail)
    async with httpx.AsyncClient(transport=transport, base_url="https://example.invalid") as raw:
        client = BinanceClient(
            "DEMO",
            api_key="key",
            api_secret="secret",
            client=raw,
            max_retries=4,
        )
        with pytest.raises(AmbiguousMutationError, match="ambiguous"):
            await client.signed_request(
                "POST",
                "/fapi/v1/order",
                {"symbol": "BTCUSDT", "newClientOrderId": "CP-test"},
            )
    assert attempts == 1


@pytest.mark.asyncio
async def test_signed_mutation_5xx_is_ambiguous_and_not_blindly_retried() -> None:
    attempts = 0

    def fail(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            503,
            json={"code": -1000, "msg": "execution status unknown"},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(fail),
        base_url="https://example.invalid",
    ) as raw:
        client = BinanceClient(
            "LIVE",
            api_key="key",
            api_secret="secret",
            client=raw,
            max_retries=4,
        )
        with pytest.raises(AmbiguousMutationError, match="query order truth") as excinfo:
            await client.signed_request(
                "POST",
                "/fapi/v1/order",
                {"symbol": "BTCUSDT", "newClientOrderId": "CP-test"},
            )

    assert attempts == 1
    assert excinfo.value.status == 503
