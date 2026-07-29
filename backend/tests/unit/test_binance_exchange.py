"""Defensive validation at the untrusted Binance response boundary."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

import pytest
from app.execution.binance_client import BinanceError
from app.execution.binance_exchange import BinanceExchange


class StubClient:
    def __init__(self, response: Any) -> None:
        self.response = response

    async def signed_request(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        return self.response


class RecordingStubClient(StubClient):
    def __init__(self, response: Any) -> None:
        super().__init__(response)
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    async def signed_request(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        self.calls.append((method, path, params))
        return self.response


class RoutedStubClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    async def signed_request(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        self.calls.append((method, path, params))
        if method == "POST":
            return {
                "clientOrderId": "CP-zero",
                "orderId": 456,
                "status": "FILLED",
                "executedQty": "0.002",
                "avgPrice": "0",
            }
        if path == "/fapi/v1/order":
            return {
                "clientOrderId": "CP-zero",
                "orderId": 456,
                "status": "FILLED",
                "executedQty": "0.002",
                "avgPrice": "0",
            }
        if path == "/fapi/v1/userTrades":
            return [
                {
                    "orderId": 456,
                    "id": 1,
                    "side": "BUY",
                    "qty": "0.001",
                    "price": "64900",
                    "commission": "0.01",
                    "realizedPnl": "0",
                    "time": int(dt.datetime(2026, 1, 1, tzinfo=dt.UTC).timestamp() * 1000),
                },
                {
                    "orderId": 456,
                    "id": 2,
                    "side": "BUY",
                    "qty": "0.001",
                    "price": "65100",
                    "commission": "0.01",
                    "realizedPnl": "0",
                    "time": int(dt.datetime(2026, 1, 1, tzinfo=dt.UTC).timestamp() * 1000),
                },
            ]
        raise AssertionError(f"unexpected request: {method} {path}")


class AlgoStubClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    async def signed_request(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        self.calls.append((method, path, params))
        if method == "POST" and path == "/fapi/v1/algoOrder":
            return {
                "algoId": 789,
                "clientAlgoId": "CP-stop",
                "algoStatus": "NEW",
                "algoType": "CONDITIONAL",
            }
        if method == "GET" and path == "/fapi/v1/order":
            raise BinanceError("order does not exist", code=-2013)
        if method == "GET" and path == "/fapi/v1/algoOrder":
            return {
                "algoId": 789,
                "clientAlgoId": "CP-stop",
                "algoStatus": "NEW",
                "actualOrderId": "",
            }
        if method == "DELETE" and path == "/fapi/v1/order":
            raise BinanceError("unknown order", code=-2011)
        if method == "DELETE" and path == "/fapi/v1/algoOrder":
            return {
                "algoId": 789,
                "clientAlgoId": "CP-stop",
                "code": "200",
                "msg": "success",
            }
        raise AssertionError(f"unexpected request: {method} {path}")


@pytest.mark.asyncio
async def test_position_response_rejects_empty_and_cross_symbol_rows() -> None:
    with pytest.raises(BinanceError, match="exactly one"):
        await BinanceExchange(StubClient([])).get_position("BTCUSDT")  # type: ignore[arg-type]

    wrong = [{"symbol": "ETHUSDT", "positionAmt": "1", "entryPrice": "100"}]
    with pytest.raises(BinanceError, match="symbol mismatch"):
        await BinanceExchange(StubClient(wrong)).get_position("BTCUSDT")  # type: ignore[arg-type]


def test_order_response_requires_matching_identity_and_valid_status() -> None:
    valid = {
        "clientOrderId": "CP-expected",
        "orderId": 123,
        "status": "FILLED",
        "executedQty": "0.01",
        "avgPrice": "65000",
    }
    result = BinanceExchange._to_result(valid, expected_client_order_id="CP-expected")
    assert result.client_order_id == "CP-expected"

    with pytest.raises(BinanceError, match="identity mismatch"):
        BinanceExchange._to_result(valid, expected_client_order_id="CP-other")

    invalid = {**valid, "status": "SURPRISE"}
    with pytest.raises(BinanceError, match="invalid status"):
        BinanceExchange._to_result(invalid)


@pytest.mark.asyncio
async def test_market_order_requests_final_result_fill() -> None:
    response = {
        "clientOrderId": "CP-result",
        "orderId": 123,
        "status": "FILLED",
        "executedQty": "0.001",
        "avgPrice": "65000",
    }
    client = RecordingStubClient(response)

    result = await BinanceExchange(client).place_market(  # type: ignore[arg-type]
        "BTCUSDT",
        "BUY",
        Decimal("0.001"),
        client_order_id="CP-result",
    )

    assert result.filled_qty == Decimal("0.001")
    assert client.calls[0][2]["newOrderRespType"] == "RESULT"  # type: ignore[index]


@pytest.mark.asyncio
async def test_market_order_recovers_zero_average_from_account_trades() -> None:
    client = RoutedStubClient()

    result = await BinanceExchange(client).place_market(  # type: ignore[arg-type]
        "BTCUSDT",
        "BUY",
        Decimal("0.002"),
        client_order_id="CP-zero",
    )

    assert result.status == "FILLED"
    assert result.filled_qty == Decimal("0.002")
    assert result.avg_price == Decimal("65000")
    assert result.raw["price_source"] == "account_trades"


@pytest.mark.asyncio
async def test_stop_market_uses_algo_api_and_supports_query_cancel() -> None:
    client = AlgoStubClient()
    exchange = BinanceExchange(client)  # type: ignore[arg-type]

    placed = await exchange.place_stop_market(
        "BTCUSDT",
        "SELL",
        Decimal("0.001"),
        Decimal("60000"),
        client_order_id="CP-stop",
    )
    queried = await exchange.get_order("BTCUSDT", "CP-stop")
    canceled = await exchange.cancel_order("BTCUSDT", "CP-stop")

    assert placed.status == "NEW"
    assert queried.status == "NEW"
    assert canceled.status == "CANCELED"
    post = client.calls[0]
    assert post[:2] == ("POST", "/fapi/v1/algoOrder")
    assert post[2] == {
        "algoType": "CONDITIONAL",
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "STOP_MARKET",
        "quantity": "0.001",
        "triggerPrice": "60000",
        "clientAlgoId": "CP-stop",
        "reduceOnly": "true",
        "workingType": "MARK_PRICE",
    }
