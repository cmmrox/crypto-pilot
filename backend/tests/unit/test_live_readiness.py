"""Read-only Binance LIVE readiness verification tests."""

from __future__ import annotations

from typing import Any

import pytest
from app.execution.live_readiness import API_RESTRICTIONS_URL, verify_live_readiness


class FakeSignedClient:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    async def signed_request(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        self.calls.append((method, path))
        return self.responses[path]


def _responses() -> dict[str, Any]:
    return {
        API_RESTRICTIONS_URL: {
            "ipRestrict": True,
            "enableReading": True,
            "enableWithdrawals": False,
            "enableMargin": False,
            "enableFutures": True,
            "permitsUniversalTransfer": False,
            "enableVanillaOptions": False,
            "enableSpotAndMarginTrading": False,
            "enablePortfolioMarginTrading": False,
            "enableFixApiTrade": False,
        },
        "/fapi/v1/positionSide/dual": {"dualSidePosition": False},
        "/fapi/v1/multiAssetsMargin": {"multiAssetsMargin": False},
        "/fapi/v2/positionRisk": [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.000",
                "marginType": "isolated",
                "leverage": "3",
            }
        ],
        "/fapi/v1/openOrders": [],
    }


@pytest.mark.asyncio
async def test_live_readiness_accepts_only_safe_flat_account() -> None:
    client = FakeSignedClient(_responses())

    result = await verify_live_readiness(client, required_leverage=3)

    assert result.ready
    assert result.issues == ()
    assert result.open_position_count == 0
    assert result.btcusdt_leverage == 3
    assert all(method == "GET" for method, _path in client.calls)


@pytest.mark.asyncio
async def test_live_readiness_reports_every_unsafe_account_control() -> None:
    responses = _responses()
    responses[API_RESTRICTIONS_URL].update(
        {
            "ipRestrict": False,
            "enableWithdrawals": True,
            "permitsUniversalTransfer": True,
        }
    )
    responses["/fapi/v1/positionSide/dual"] = {"dualSidePosition": True}
    responses["/fapi/v1/multiAssetsMargin"] = {"multiAssetsMargin": True}
    responses["/fapi/v2/positionRisk"] = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "0.001",
            "marginType": "cross",
            "leverage": "20",
        },
        {
            "symbol": "ETHUSDT",
            "positionAmt": "-0.01",
            "marginType": "cross",
            "leverage": "10",
        },
    ]
    responses["/fapi/v1/openOrders"] = [{"orderId": 1}]

    result = await verify_live_readiness(
        FakeSignedClient(responses),
        required_leverage=3,
    )

    assert not result.ready
    assert result.open_position_count == 2
    assert result.open_order_count == 1
    assert result.btcusdt_margin_type == "cross"
    assert result.btcusdt_leverage == 20
    assert any("withdrawals" in issue for issue in result.issues)
    assert any("Hedge Mode" in issue for issue in result.issues)
    assert any("existing LIVE positions" in issue for issue in result.issues)
    assert any("active strategy setting (3x)" in issue for issue in result.issues)


@pytest.mark.asyncio
async def test_live_readiness_uses_active_strategy_leverage_and_can_allow_resume_state() -> None:
    responses = _responses()
    responses["/fapi/v2/positionRisk"][0]["positionAmt"] = "0.001"
    responses["/fapi/v2/positionRisk"][0]["leverage"] = "6"
    responses["/fapi/v1/openOrders"] = [{"orderId": 1}]

    resumed = await verify_live_readiness(
        FakeSignedClient(responses),
        required_leverage=6,
        require_flat=False,
    )
    first_start = await verify_live_readiness(
        FakeSignedClient(responses),
        required_leverage=6,
        require_flat=True,
    )

    assert resumed.ready
    assert not first_start.ready
    assert any("existing LIVE positions" in issue for issue in first_start.issues)
    assert any("existing LIVE open orders" in issue for issue in first_start.issues)
