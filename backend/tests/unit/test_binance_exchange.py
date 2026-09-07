"""Defensive validation at the untrusted Binance response boundary."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

import pytest
from app.execution.binance_client import AmbiguousMutationError, BinanceError
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


class AmbiguousPlacementStubClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    async def signed_request(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        self.calls.append((method, path, params))
        if method == "POST":
            raise AmbiguousMutationError("execution status unknown", status=503)
        if method == "GET" and path == "/fapi/v1/order":
            return {
                "clientOrderId": "CP-recovered",
                "orderId": 9001,
                "status": "FILLED",
                "executedQty": "0.001",
                "avgPrice": "65000",
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
async def test_market_order_recovers_ambiguous_5xx_from_idempotent_order_query() -> None:
    client = AmbiguousPlacementStubClient()

    result = await BinanceExchange(client).place_market(  # type: ignore[arg-type]
        "BTCUSDT",
        "BUY",
        Decimal("0.001"),
        client_order_id="CP-recovered",
    )

    assert result.status == "FILLED"
    assert result.filled_qty == Decimal("0.001")
    assert result.avg_price == Decimal("65000")
    assert [call[:2] for call in client.calls] == [
        ("POST", "/fapi/v1/order"),
        ("GET", "/fapi/v1/order"),
    ]


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


async def test_account_projection_keeps_decimal_precision_and_omits_flat_positions():
    data = {
        "totalWalletBalance": "123456789.12345678",
        "availableBalance": "12.00000001",
        "totalUnrealizedProfit": "-0.00000001",
        "positions": [
            {"symbol": "BTCUSDT", "positionAmt": "0.001", "entryPrice": "61234.12345678"},
            {"symbol": "ETHUSDT", "positionAmt": "0", "entryPrice": "0"},
        ],
    }
    account = await BinanceExchange(StubClient(data)).get_account()
    assert account.balance == Decimal("123456789.12345678")
    assert account.available == Decimal("12.00000001")
    assert account.unrealized_pnl == Decimal("-0.00000001")
    assert len(account.positions) == 1
    assert account.positions[0].entry_price == Decimal("61234.12345678")


async def test_funding_projection_preserves_income_identity_and_utc():
    instant = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    client = RecordingStubClient(
        [{"tranId": 42, "income": "-0.00000001", "time": int(instant.timestamp() * 1000)}]
    )
    rows = await BinanceExchange(client).get_funding_income("BTCUSDT", start_at=instant)
    assert rows[0].exchange_income_id == "42"
    assert rows[0].amount == Decimal("-0.00000001")
    assert rows[0].occurred_at == instant
    assert client.calls[0][2]["startTime"] == int(instant.timestamp() * 1000)


@pytest.mark.parametrize(
    "row,expected",
    [
        ([], "shape"),
        ({}, "identity"),
        ({"clientOrderId": "x", "orderId": 1, "status": "UNKNOWN"}, "status"),
        ({"clientOrderId": "x", "orderId": 1, "status": "NEW", "executedQty": "-1"}, "negative"),
    ],
)
def test_untrusted_regular_order_rejected(row, expected):
    with pytest.raises(BinanceError, match=expected):
        BinanceExchange._to_result(row)


@pytest.mark.parametrize(
    "row,expected",
    [
        ([], "shape"),
        ({}, "identity"),
        ({"clientAlgoId": "x", "algoId": 1, "algoStatus": "UNKNOWN"}, "status"),
    ],
)
def test_untrusted_algo_order_rejected(row, expected):
    with pytest.raises(BinanceError, match=expected):
        BinanceExchange._to_algo_result(row)


async def test_unconfirmed_algo_cancel_is_rejected():
    from unittest.mock import AsyncMock

    client = AsyncMock()
    client.signed_request.side_effect = [
        BinanceError("missing", code=-2013),
        {"code": 500, "algoId": 1},
    ]
    with pytest.raises(BinanceError, match="not confirmed"):
        await BinanceExchange(client).cancel_order("BTCUSDT", "cancel-id")


async def test_missing_order_retries_reads_but_does_not_place_again(monkeypatch):
    from unittest.mock import AsyncMock

    client = AsyncMock()
    client.signed_request.side_effect = BinanceError("missing", code=-2013)
    delay = AsyncMock()
    monkeypatch.setattr("app.execution.binance_exchange.asyncio.sleep", delay)
    with pytest.raises(BinanceError, match="missing"):
        await BinanceExchange(client).get_order("BTCUSDT", "known-id")
    assert client.signed_request.call_count == 6
    assert all(call.args[0] == "GET" for call in client.signed_request.call_args_list)
    assert delay.await_count == 2
