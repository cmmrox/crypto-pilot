"""Integration tests for security hardening + guarded settings (QA-9)."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import auth_headers


async def _headers(client: httpx.AsyncClient, _secret: str) -> dict[str, str]:
    return await auth_headers(client)


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
        "/api/auth/me",
        "/api/events",
        "/api/market/status",
        "/api/trades",
        "/api/monthly",
        "/api/bot/status",
        "/api/overview",
        "/api/news/latest",
        "/api/strategies",
        "/api/settings/sms",
        "/api/settings/codex/status",
        "/api/settings/security",
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
    from app.core.config import get_settings

    h = await _headers(app_client, owner)
    # Bot is stopped by default.
    bad = await app_client.put("/api/settings/environment", json={"environment": "LIVE"}, headers=h)
    assert bad.status_code == 400  # missing confirm
    locked = await app_client.put(
        "/api/settings/environment",
        json={"environment": "LIVE", "confirm": "LIVE"},
        headers=h,
    )
    assert locked.status_code == 403

    settings = get_settings()
    settings.live_trading_approved = True
    settings.live_key_permissions_verified = True
    good = await app_client.put(
        "/api/settings/environment", json={"environment": "LIVE", "confirm": "LIVE"}, headers=h
    )
    assert good.status_code == 200


@pytest.mark.asyncio
async def test_strategy_switch_guarded(app_client: httpx.AsyncClient, owner: str) -> None:
    h = await _headers(app_client, owner)
    ok = await app_client.put(
        "/api/settings/strategy",
        json={"name": "trend_rider_v52_4h"},
        headers=h,
    )
    assert ok.status_code == 200
    bad = await app_client.put("/api/settings/strategy", json={"name": "nope"}, headers=h)
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_strategy_switch_rejects_open_trade(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    import datetime as dt
    from decimal import Decimal

    from app.db.models import Trade
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        session.add(
            Trade(
                opened_at=dt.datetime.now(dt.UTC),
                side="LONG",
                entry_px=Decimal("50000"),
                qty=Decimal("0.001"),
                remaining_qty=Decimal("0.001"),
                strategy="trend_rider_v6_4h",
                strategy_release="6.0",
                strategy_interval="4h",
                environment="DEMO",
            )
        )
        await session.commit()

    response = await app_client.put(
        "/api/settings/strategy",
        json={"name": "trend_rider_v52_4h"},
        headers=await _headers(app_client, owner),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == ("Close the active position before changing strategy.")


@pytest.mark.asyncio
async def test_body_size_limit(app_client: httpx.AsyncClient, owner: str) -> None:
    huge = "x" * 2_000_000
    resp = await app_client.post(
        "/api/auth/login", content=huge, headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_body_size_limit_rejects_lengthless_stream(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    async def oversized_body() -> object:
        for _ in range(11):
            yield b"x" * 100_000

    resp = await app_client.post(
        "/api/auth/login",
        content=oversized_body(),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413
