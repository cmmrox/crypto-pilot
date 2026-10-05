"""Safety and protocol checks for the CI-only synthetic public-market backend."""

from types import SimpleNamespace

import pytest
import market_backend
from app.core import config
from app.execution.binance_client import BinanceClient, BinanceError


@pytest.mark.parametrize(
    "override",
    [
        {"environment": "production"},
        {"environment": "development"},
        {"otp_test_mode": False},
        {"database_url": "postgresql://localhost/cryptopilot"},
        {"live_trading_approved": True},
        {"live_key_permissions_verified": True},
    ],
)
def test_fixture_refuses_nonisolated_or_live_approved_stack(monkeypatch, override):
    values = dict(
        environment="test",
        otp_test_mode=True,
        database_url="postgresql://localhost/cryptopilot_ci_e2e",
        live_trading_approved=False,
        live_key_permissions_verified=False,
    )
    values.update(override)
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(**values))
    with pytest.raises(RuntimeError, match="isolated"):
        market_backend.require_test_stack()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,signed", [("GET", True), ("POST", False), ("DELETE", False)]
)
async def test_fixture_never_accepts_signed_requests_or_mutations(method, signed):
    with pytest.raises(BinanceError, match="refuses"):
        await market_backend.public_response(
            None, method, "/fapi/v1/order", signed=signed
        )


@pytest.mark.asyncio
async def test_rest_fixture_round_trips_real_decoder_and_is_contiguous(monkeypatch):
    monkeypatch.setattr(BinanceClient, "_request", market_backend.public_response)
    async with BinanceClient("DEMO") as client:
        rows = await client.get_klines("BTCUSDT", "4h", limit=120)
        assert len(rows) == 120 and all(row.is_closed for row in rows)
        assert all(
            right.open_time_ms - left.open_time_ms == 14400000
            for left, right in zip(rows, rows[1:])
        )
        # The repair pagination must honor explicit start/end boundaries.
        start = rows[10].open_time_ms
        end = rows[19].open_time_ms
        page = await client.get_klines(
            "BTCUSDT", "4h", limit=5, start_time_ms=start, end_time_ms=end
        )
        assert [row.open_time_ms for row in page] == [
            row.open_time_ms for row in rows[10:15]
        ]
        assert abs(await client.clock_drift_ms()) < 1000
