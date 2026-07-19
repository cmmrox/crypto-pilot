"""Integration tests for market status, backfill, and credentials API (QA-2)."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from app.execution.binance_client import Kline

from tests.conftest import OWNER_PASSWORD, auth_headers

STEP_MS = 4 * 60 * 60 * 1000
BASE_MS = 1784318400000


async def _auth_headers(client: httpx.AsyncClient, _secret: str) -> dict[str, str]:
    return await auth_headers(client)


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
            "current_password": OWNER_PASSWORD,
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

    from app.db.models import ApiCredential
    from app.db.session import get_sessionmaker
    from sqlalchemy import select

    async with get_sessionmaker()() as session:
        row = (await session.execute(select(ApiCredential))).scalar_one()
        assert row.api_key is None
        assert row.api_key_encrypted is not None
        assert "DEMOKEY1234ABCD" not in row.api_key_encrypted


@pytest.mark.asyncio
async def test_credential_replacement_requires_current_password(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    headers = await _auth_headers(app_client, owner)
    response = await app_client.put(
        "/api/settings/credentials",
        json={
            "environment": "DEMO",
            "service": "binance",
            "api_key": "DEMOKEY",
            "api_secret": "DEMOSECRET",
            "current_password": "wrong",
        },
        headers=headers,
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_credential_status_unconfigured(app_client: httpx.AsyncClient, owner: str) -> None:
    headers = await _auth_headers(app_client, owner)
    st = await app_client.get("/api/settings/credentials/LIVE/binance", headers=headers)
    assert st.json()["configured"] is False


@pytest.mark.asyncio
async def test_credential_status_rejects_notifylk_and_cannot_break_sms_config(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    from app.db.models import ApiCredential
    from app.db.session import get_sessionmaker
    from app.services.notify_config import get_notify_config, save_notify_config
    from sqlalchemy import select

    async with get_sessionmaker()() as session:
        await save_notify_config(
            session,
            user_id="notify-user",
            api_key="notify-api-key",
            sender_id="CryptoPilot",
            phone="94711234567",
        )
        await session.commit()

    headers = await _auth_headers(app_client, owner)
    response = await app_client.get("/api/settings/credentials/ALL/notifylk", headers=headers)
    assert response.status_code == 422

    async with get_sessionmaker()() as session:
        config = await get_notify_config(session)
        row = (
            await session.execute(select(ApiCredential).where(ApiCredential.service == "notifylk"))
        ).scalar_one()
        assert config is not None and config.user_id == "notify-user"
        assert row.api_key is None
        assert row.api_key_encrypted is not None
        assert "notify-user" not in row.api_key_encrypted


@pytest.mark.asyncio
async def test_legacy_notify_user_id_is_encrypted_on_first_read(
    app_client: httpx.AsyncClient,
) -> None:
    import json

    from app.core.config import get_settings
    from app.core.crypto import encrypt
    from app.db.models import ApiCredential
    from app.db.session import get_sessionmaker
    from app.services.notify_config import get_notify_config
    from sqlalchemy import select

    master = get_settings().master_key
    async with get_sessionmaker()() as session:
        session.add(
            ApiCredential(
                environment="ALL",
                service="notifylk",
                api_key="legacy-notify-user",
                api_key_encrypted=None,
                secret_encrypted=encrypt(
                    json.dumps(
                        {
                            "api_key": "notify-api-key",
                            "sender_id": "CryptoPilot",
                            "phone": "94711234567",
                        }
                    ),
                    master,
                ),
            )
        )
        await session.commit()

        config = await get_notify_config(session)
        await session.commit()
        assert config is not None and config.user_id == "legacy-notify-user"

        row = (
            await session.execute(select(ApiCredential).where(ApiCredential.service == "notifylk"))
        ).scalar_one()
        assert row.api_key is None
        assert row.api_key_encrypted is not None
        assert "legacy-notify-user" not in row.api_key_encrypted


@pytest.mark.asyncio
async def test_plaintext_key_migration_clears_every_legacy_slot(
    app_client: httpx.AsyncClient,
) -> None:
    from app.core.config import get_settings
    from app.core.crypto import decrypt, encrypt
    from app.db.models import ApiCredential
    from app.db.session import get_sessionmaker
    from app.services.credentials import migrate_plaintext_keys
    from sqlalchemy import select

    master = get_settings().master_key
    async with get_sessionmaker()() as session:
        session.add_all(
            [
                ApiCredential(
                    environment="DEMO",
                    service="binance",
                    api_key="legacy-binance-key",
                    api_key_encrypted=None,
                    secret_encrypted=encrypt("legacy-secret", master),
                ),
                ApiCredential(
                    environment="ALL",
                    service="notifylk",
                    api_key="legacy-notify-user",
                    api_key_encrypted=None,
                    secret_encrypted=encrypt("{}", master),
                ),
            ]
        )
        await session.commit()

        assert await migrate_plaintext_keys(session) == 2
        await session.commit()
        rows = (
            await session.execute(
                select(ApiCredential).order_by(
                    ApiCredential.environment, ApiCredential.service
                )
            )
        ).scalars()
        values = list(rows)
        assert all(row.api_key is None for row in values)
        assert {
            decrypt(row.api_key_encrypted, master)
            for row in values
            if row.api_key_encrypted is not None
        } == {"legacy-binance-key", "legacy-notify-user"}


@pytest.mark.asyncio
async def test_connection_test_public_only(
    app_client: httpx.AsyncClient, owner: str, _mock_binance: None
) -> None:
    headers = await _auth_headers(app_client, owner)
    resp = await app_client.post("/api/settings/credentials/DEMO/binance/test", headers=headers)
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
