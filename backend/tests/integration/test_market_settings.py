"""Integration tests for market status, backfill, and credentials API (QA-2)."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from app.execution.binance_client import Kline

from tests.conftest import OWNER_EMAIL, OWNER_PASSWORD, current_totp

STEP_MS = 4 * 60 * 60 * 1000
BASE_MS = 1784318400000


async def _auth_headers(client: httpx.AsyncClient, secret: str) -> dict[str, str]:
    r = await client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    totp_token = r.json()["totp_token"]
    r = await client.post(
        "/api/auth/totp",
        json={"code": current_totp(secret)},
        headers={"Authorization": f"Bearer {totp_token}"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _fake_klines(n: int) -> list[Kline]:
    out = []
    for i in range(n):
        t = BASE_MS + i * STEP_MS
        out.append(
            Kline(
                open_time_ms=t,
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("105"),
                volume=Decimal("5"),
                close_time_ms=t + STEP_MS - 1,
                is_closed=True,
            )
        )
    return out


@pytest.fixture()
def _mock_binance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace network calls on BinanceClient with deterministic fakes."""
    from app.execution import binance_client as bc

    async def fake_klines(self: object, symbol: str, interval: str, *, limit: int = 500):  # type: ignore[no-untyped-def]
        return _fake_klines(10)

    async def fake_drift(self: object) -> int:
        return 12

    monkeypatch.setattr(bc.BinanceClient, "get_klines", fake_klines)
    monkeypatch.setattr(bc.BinanceClient, "clock_drift_ms", fake_drift)


@pytest.mark.asyncio
async def test_market_status_requires_auth(app_client: httpx.AsyncClient, owner: str) -> None:
    assert (await app_client.get("/api/market/status")).status_code == 401


@pytest.mark.asyncio
async def test_backfill_then_status_reports_candles(
    app_client: httpx.AsyncClient, owner: str, _mock_binance: None
) -> None:
    headers = await _auth_headers(app_client, owner)
    resp = await app_client.post("/api/market/backfill", headers=headers)
    assert resp.status_code == 200, resp.text
    status = resp.json()
    assert status["candles_stored"] == 10
    assert status["gaps"] == 0
    assert status["exchange_reachable"] is True
    assert status["symbol"] == "BTCUSDT"
    assert status["seconds_to_next_close"] > 0


@pytest.mark.asyncio
async def test_credentials_are_write_only(app_client: httpx.AsyncClient, owner: str) -> None:
    headers = await _auth_headers(app_client, owner)
    # Save a DEMO binance credential.
    put = await app_client.put(
        "/api/settings/credentials",
        json={
            "environment": "DEMO",
            "service": "binance",
            "api_key": "DEMOKEY1234ABCD",
            "api_secret": "supersecretvalue",
        },
        headers=headers,
    )
    assert put.status_code == 200
    # Status shows configured + masked hint, never the secret.
    st = await app_client.get("/api/settings/credentials/DEMO/binance", headers=headers)
    body = st.json()
    assert body["configured"] is True
    assert body["key_hint"] == "····ABCD"
    assert "supersecretvalue" not in st.text
    assert "api_secret" not in body


@pytest.mark.asyncio
async def test_credential_status_unconfigured(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    headers = await _auth_headers(app_client, owner)
    st = await app_client.get("/api/settings/credentials/LIVE/binance", headers=headers)
    assert st.json()["configured"] is False


@pytest.mark.asyncio
async def test_connection_test_public_only(
    app_client: httpx.AsyncClient, owner: str, _mock_binance: None
) -> None:
    headers = await _auth_headers(app_client, owner)
    resp = await app_client.post(
        "/api/settings/credentials/DEMO/binance/test", headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "market data reachable" in body["detail"].lower()


@pytest.mark.asyncio
async def test_events_endpoint_lists_audit(app_client: httpx.AsyncClient, owner: str) -> None:
    headers = await _auth_headers(app_client, owner)
    # The login above recorded a security event; the list should include it.
    resp = await app_client.get("/api/events", headers=headers)
    assert resp.status_code == 200
    events = resp.json()
    assert any(e["category"] == "security" for e in events)
    # Filter by category.
    filtered = await app_client.get("/api/events?category=security", headers=headers)
    assert all(e["category"] == "security" for e in filtered.json())
