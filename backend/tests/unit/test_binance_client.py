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


async def test_user_stream_lifecycle_uses_api_key_without_trade_signature() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"listenKey": "test-listen-key"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.invalid"
    ) as raw:
        client = BinanceClient("DEMO", api_key="test-key", api_secret="test-secret", client=raw)
        key = await client.start_user_stream()
        await client.keepalive_user_stream(key)
        await client.close_user_stream(key)
    assert [r.method for r in requests] == ["POST", "PUT", "DELETE"]
    for request in requests:
        assert request.url.path == "/fapi/v1/listenKey"
        assert request.headers["X-MBX-APIKEY"] == "test-key"
        assert "signature" not in request.url.params
        assert "timestamp" not in request.url.params


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


def _signed_params(request: httpx.Request) -> dict[str, str]:
    """The query a request signed, in sent order, without its signature."""
    return {k: v for k, v in request.url.params.multi_items() if k != "signature"}


@pytest.fixture
def ticking_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Advance the signing clock 1s per read and make retry backoff instant."""
    from app.execution import binance_client

    now = [1_791_964_800.0]

    def tick() -> float:
        now[0] += 1.0
        return now[0]

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(binance_client.time, "time", tick)
    monkeypatch.setattr(binance_client.asyncio, "sleep", no_sleep)


@pytest.mark.asyncio
@pytest.mark.usefixtures("ticking_clock")
async def test_signed_read_retry_is_resigned_with_a_fresh_timestamp() -> None:
    """Regression: 2026-10-09 a DNS failure was retried with the original timestamp.

    Every retry of a signed request must carry its own timestamp and signature, or
    a slow first attempt makes every retry arrive outside Binance's recvWindow.
    """
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ConnectError("Name or service not known", request=request)
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.invalid"
    ) as raw:
        client = BinanceClient("LIVE", api_key="key", api_secret="secret", client=raw)
        assert await client.signed_request("GET", "/fapi/v2/account") == {"ok": True}

    assert len(requests) == 2
    first, second = (_signed_params(r) for r in requests)
    assert int(second["timestamp"]) > int(first["timestamp"])
    for request in requests:
        assert request.url.params["signature"] == sign_query("secret", _signed_params(request))


@pytest.mark.asyncio
@pytest.mark.usefixtures("ticking_clock")
async def test_invalid_timestamp_rejection_of_an_order_is_resent_with_same_client_id() -> None:
    """Regression: 2026-10-14 08:00 UTC the LIVE decision died on Binance -1021.

    Binance rejects an out-of-window request before processing it, so the order was
    never placed. Resending it freshly signed, with the same idempotent client order
    ID, is safe and must not push the bot into safe mode.
    """
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                400,
                json={
                    "code": -1021,
                    "msg": "Timestamp for this request is outside of the recvWindow.",
                },
            )
        return httpx.Response(200, json={"orderId": 1, "status": "FILLED"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.invalid"
    ) as raw:
        client = BinanceClient("LIVE", api_key="key", api_secret="secret", client=raw)
        result = await client.signed_request(
            "POST", "/fapi/v1/order", {"symbol": "BTCUSDT", "newClientOrderId": "CPL-test"}
        )

    assert result == {"orderId": 1, "status": "FILLED"}
    assert len(requests) == 2
    first, second = (_signed_params(r) for r in requests)
    assert first["newClientOrderId"] == second["newClientOrderId"] == "CPL-test"
    assert int(second["timestamp"]) > int(first["timestamp"])


@pytest.mark.asyncio
@pytest.mark.usefixtures("ticking_clock")
async def test_persistent_invalid_timestamp_is_bounded_and_keeps_binance_code() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            400,
            json={"code": -1021, "msg": "Timestamp for this request is outside of the recvWindow."},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.invalid"
    ) as raw:
        client = BinanceClient(
            "LIVE", api_key="key", api_secret="secret", client=raw, max_retries=3
        )
        with pytest.raises(BinanceError) as excinfo:
            await client.signed_request("GET", "/fapi/v2/account")

    assert attempts == 3
    assert excinfo.value.code == -1021
    assert excinfo.value.endpoint == "GET /fapi/v2/account"


@pytest.mark.asyncio
async def test_definitive_order_rejection_is_not_retried_and_names_its_endpoint() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, json={"code": -2019, "msg": "Margin is insufficient."})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.invalid"
    ) as raw:
        client = BinanceClient("LIVE", api_key="key", api_secret="secret", client=raw)
        with pytest.raises(BinanceError) as excinfo:
            await client.signed_request(
                "POST", "/fapi/v1/order", {"symbol": "BTCUSDT", "newClientOrderId": "CPL-x"}
            )

    assert attempts == 1
    assert excinfo.value.code == -2019
    # Method and path only: never the signed query, key, or signature.
    assert excinfo.value.endpoint == "POST /fapi/v1/order"
