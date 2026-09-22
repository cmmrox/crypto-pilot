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
    assert "trend_rider_v6_4h" in by_name and "trend_rider_v52_4h" in by_name
    v6 = by_name["trend_rider_v6_4h"]
    assert v6["parity_verified"] is True
    assert v6["direction"] == "LONG + SHORT"
    assert v6["active"] is True  # default active strategy
    assert by_name["trend_rider_v52_4h"]["direction"] == "LONG ONLY"
    assert v6["interval"] == "4h"
    assert v6["display_name"] == "Atlas 6 · 4h"
    assert v6["summary"]
    assert v6["risk_controls"]
    assert v6["params"]["stop_atr"] == 2.5


async def test_strategy_names_are_distinct_and_ids_remain_compatible(app_client, owner):
    headers = await auth_headers(app_client)
    response = await app_client.get("/api/strategies", headers=headers)
    assert response.status_code == 200
    names = {row["name"]: row["display_name"] for row in response.json()}
    assert names == {
        "trend_rider_v52_4h": "Atlas 5.2 · 4h",
        "trend_rider_v6_4h": "Atlas 6 · 4h",
        "trend_rider_refined_v1_4h": "Atlas 6 Trail · 4h",
        "atlas_dual_v1_4h": "Atlas 7 Dual · 4h",
    }
