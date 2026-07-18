"""Integration tests for security hardening + guarded settings (QA-9)."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import OWNER_EMAIL, OWNER_PASSWORD, current_totp


async def _headers(client: httpx.AsyncClient, secret: str) -> dict[str, str]:
    r = await client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    tok = r.json()["totp_token"]
    r = await client.post("/api/auth/totp", json={"code": current_totp(secret)},
                          headers={"Authorization": f"Bearer {tok}"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_security_headers_present(app_client: httpx.AsyncClient, owner: str) -> None:
    resp = await app_client.get("/health")
    h = resp.headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert "content-security-policy" in h
    assert "frame-ancestors 'none'" in h["content-security-policy"]


@pytest.mark.asyncio
async def test_authz_sweep_protected_routes_reject_anonymous(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    protected_get = [
        "/api/auth/me", "/api/events", "/api/market/status", "/api/trades",
        "/api/monthly", "/api/bot/status", "/api/overview", "/api/news/latest",
        "/api/strategies", "/api/settings/sms", "/api/settings/codex/status",
    ]
    for path in protected_get:
        assert (await app_client.get(path)).status_code == 401, path
    protected_post = ["/api/bot/start", "/api/ops/kill", "/api/news/refresh"]
    for path in protected_post:
        assert (await app_client.post(path)).status_code == 401, path


@pytest.mark.asyncio
async def test_environment_switch_blocked_while_running(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    from app.bot.service import bot_service
    from app.db.session import get_sessionmaker

    from tests.fakes import FakeExchange

    h = await _headers(app_client, owner)
    async with get_sessionmaker()() as s:
        await bot_service.start(s, FakeExchange(), by="test")
        await s.commit()
    resp = await app_client.put(
        "/api/settings/environment", json={"environment": "DEMO"}, headers=h
    )
    assert resp.status_code == 409  # bot running


@pytest.mark.asyncio
async def test_live_switch_requires_typed_confirm(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    h = await _headers(app_client, owner)
    # Bot is stopped by default.
    bad = await app_client.put("/api/settings/environment", json={"environment": "LIVE"}, headers=h)
    assert bad.status_code == 400  # missing confirm
    good = await app_client.put(
        "/api/settings/environment", json={"environment": "LIVE", "confirm": "LIVE"}, headers=h
    )
    assert good.status_code == 200


@pytest.mark.asyncio
async def test_strategy_switch_guarded(app_client: httpx.AsyncClient, owner: str) -> None:
    h = await _headers(app_client, owner)
    ok = await app_client.put("/api/settings/strategy", json={"name": "trend_rider_v52"}, headers=h)
    assert ok.status_code == 200
    bad = await app_client.put("/api/settings/strategy", json={"name": "nope"}, headers=h)
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_body_size_limit(app_client: httpx.AsyncClient, owner: str) -> None:
    huge = "x" * 2_000_000
    resp = await app_client.post(
        "/api/auth/login", content=huge, headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 413
