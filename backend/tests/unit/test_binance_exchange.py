"""Defensive validation at the untrusted Binance response boundary."""

from __future__ import annotations

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
