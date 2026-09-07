"""Public data response validation and bounded client retries, no external network."""

from unittest.mock import AsyncMock

import httpx
import pytest
from app.execution.binance_client import BinanceClient, BinanceError


@pytest.mark.parametrize(
    "response", [{}, {"symbol": "ETHUSDT"}, {"symbol": "BTCUSDT", "markPrice": "0", "time": 1}]
)
async def test_invalid_mark_quote_rejected(response):
    client = AsyncMock()
    client.request.return_value = httpx.Response(200, json=response)
    exchange = BinanceClient(environment="DEMO", client=client)
    with pytest.raises(BinanceError):
        await exchange.get_mark_price("BTCUSDT")


@pytest.mark.parametrize("response", [{}, {"symbol": "BTCUSDT"}])
async def test_invalid_ticker_rejected(response):
    client = AsyncMock()
    client.request.return_value = httpx.Response(200, json=response)
    with pytest.raises(BinanceError):
        await BinanceClient(environment="DEMO", client=client).get_ticker_24h("BTCUSDT")


async def test_missing_symbol_filters_rejected_and_no_signed_credentials_required():
    client = AsyncMock()
    client.request.return_value = httpx.Response(200, json={"symbols": []})
    with pytest.raises(BinanceError, match="not found"):
        await BinanceClient(environment="DEMO", client=client).get_exchange_filters("BTCUSDT")


async def test_transport_retries_stop_at_budget(monkeypatch):
    client = AsyncMock()
    client.request.side_effect = httpx.ConnectError("network unavailable")
    monkeypatch.setattr("app.execution.binance_client.asyncio.sleep", AsyncMock())
    with pytest.raises(BinanceError, match="after 3 attempts"):
        await BinanceClient(environment="DEMO", client=client, max_retries=3).get_server_time_ms()
    assert client.request.await_count == 3


async def test_non_json_api_failure_is_reported_as_exchange_error():
    client = AsyncMock()
    client.request.return_value = httpx.Response(403, text="Forbidden")
    with pytest.raises(BinanceError, match="Forbidden"):
        await BinanceClient(environment="DEMO", client=client).get_server_time_ms()
