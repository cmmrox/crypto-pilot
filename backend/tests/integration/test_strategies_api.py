"""Integration test for the strategy library API (QA-3)."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import auth_headers


async def _headers(client: httpx.AsyncClient, _secret: str) -> dict[str, str]:
    return await auth_headers(client)


@pytest.mark.asyncio
async def test_strategies_requires_auth(app_client: httpx.AsyncClient, owner: str) -> None:
    assert (await app_client.get("/api/strategies")).status_code == 401


@pytest.mark.asyncio
async def test_strategy_library_lists_both_with_parity(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    resp = await app_client.get("/api/strategies", headers=await _headers(app_client, owner))
    assert resp.status_code == 200
    by_name = {s["name"]: s for s in resp.json()}
    assert "trend_rider_v6" in by_name and "trend_rider_v52" in by_name
    v6 = by_name["trend_rider_v6"]
    assert v6["parity_verified"] is True
    assert v6["direction"] == "LONG + SHORT"
    assert v6["active"] is True  # default active strategy
    assert by_name["trend_rider_v52"]["direction"] == "LONG ONLY"
    assert v6["params"]["stop_atr"] == 2.5
