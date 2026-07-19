"""Integration tests for the SMS-2FA authentication flow (QA-1)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from tests.conftest import (
    OWNER_EMAIL,
    OWNER_PASSWORD,
    auth_headers,
    complete_login,
    current_otp,
)


async def _login_to_otp_token(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "otp"
    assert body["phone_hint"] and body["phone_hint"].endswith("4567")
    return body["otp_token"]


@pytest.mark.asyncio
async def test_happy_path_login(app_client: httpx.AsyncClient, owner: str) -> None:
    access, refresh = await complete_login(app_client)
    me = await app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["email"] == OWNER_EMAIL
    assert refresh


@pytest.mark.asyncio
async def test_login_contract_exposes_only_sms_otp_surface(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    password_step = await app_client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert password_step.status_code == 200
    body = password_step.json()
    assert body["mode"] == "otp"
    assert body["otp_token"]
    assert "totp_token" not in body

    removed_endpoint = await app_client.post(
        "/api/auth/totp",
        json={"code": current_otp()},
        headers={"Authorization": f"Bearer {body['otp_token']}"},
    )
    assert removed_endpoint.status_code == 404

    verified = await app_client.post(
        "/api/auth/otp/verify",
        json={"code": current_otp()},
        headers={"Authorization": f"Bearer {body['otp_token']}"},
    )
    assert verified.status_code == 200
    assert verified.json()["access_token"]
    assert verified.json()["refresh_token"]


@pytest.mark.asyncio
async def test_password_step_never_issues_tokens_when_2fa_on(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    resp = await app_client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    body = resp.json()
    assert body["mode"] == "otp"
    assert body["access_token"] is None and body["refresh_token"] is None


@pytest.mark.asyncio
async def test_enabled_2fa_without_phone_never_falls_back_to_password_only(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    from app.db.models import User
    from app.db.session import get_sessionmaker
    from sqlalchemy import select

    async with get_sessionmaker()() as session:
        user = (await session.execute(select(User).where(User.email == OWNER_EMAIL))).scalar_one()
        user.phone_encrypted = None
        await session.commit()

    resp = await app_client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert resp.status_code == 401
    assert "access_token" not in resp.json()


@pytest.mark.asyncio
async def test_gateway_failure_never_issues_tokens_and_is_audited(
    app_client: httpx.AsyncClient,
    owner: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.db.models import Event
    from app.db.session import get_sessionmaker
    from app.notifier.gateway import SmsResult
    from app.services import otp as otp_service
    from sqlalchemy import select

    async def fail_delivery(*_args: object, **_kwargs: object) -> SmsResult:
        return SmsResult(False, "provider unavailable")

    monkeypatch.setattr(otp_service, "_deliver", fail_delivery)
    resp = await app_client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert resp.status_code == 401
    assert "access_token" not in resp.json()
    async with get_sessionmaker()() as session:
        event = (
            await session.execute(select(Event).where(Event.ref == f"otp_send:login:{OWNER_EMAIL}"))
        ).scalar_one()
        assert event.sms_status == "failed"
        assert "provider unavailable" not in str(event.payload_json)


@pytest.mark.asyncio
async def test_otp_pending_token_cannot_access_api(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    otp_token = await _login_to_otp_token(app_client)
    resp = await app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {otp_token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_password_rejected(app_client: httpx.AsyncClient, owner: str) -> None:
    resp = await app_client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": "wrong-password"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_otp_rejected(app_client: httpx.AsyncClient, owner: str) -> None:
    otp_token = await _login_to_otp_token(app_client)
    resp = await app_client.post(
        "/api/auth/otp/verify",
        json={"code": "000000"},
        headers={"Authorization": f"Bearer {otp_token}"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_otp_single_use(app_client: httpx.AsyncClient, owner: str) -> None:
    otp_token = await _login_to_otp_token(app_client)
    code = current_otp()
    headers = {"Authorization": f"Bearer {otp_token}"}
    first = await app_client.post("/api/auth/otp/verify", json={"code": code}, headers=headers)
    assert first.status_code == 200
    # Re-submitting the same (now consumed) challenge fails.
    second = await app_client.post("/api/auth/otp/verify", json={"code": code}, headers=headers)
    assert second.status_code == 401


@pytest.mark.asyncio
async def test_otp_locks_after_five_attempts(app_client: httpx.AsyncClient, owner: str) -> None:
    otp_token = await _login_to_otp_token(app_client)
    headers = {"Authorization": f"Bearer {otp_token}"}
    for _ in range(5):
        r = await app_client.post("/api/auth/otp/verify", json={"code": "000000"}, headers=headers)
        assert r.status_code == 401
    # Even the correct code no longer works. The per-challenge budget is
    # exhausted and the account-wide failure budget is now locked.
    r = await app_client.post("/api/auth/otp/verify", json={"code": current_otp()}, headers=headers)
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_otp_token_not_bound_to_other_challenge(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    # Start two logins; the newer code must not verify against the older token's
    # challenge (token↔challenge binding).
    token_a = await _login_to_otp_token(app_client)
    await _login_to_otp_token(app_client)
    code_b = current_otp()  # the most recent code
    resp = await app_client.post(
        "/api/auth/otp/verify",
        json={"code": code_b},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_resend_cooldown(app_client: httpx.AsyncClient, owner: str) -> None:
    otp_token = await _login_to_otp_token(app_client)
    headers = {"Authorization": f"Bearer {otp_token}"}
    # Immediate resend hits the 60s cooldown.
    resp = await app_client.post("/api/auth/otp/resend", headers=headers)
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_send_cap_per_hour(app_client: httpx.AsyncClient, owner: str) -> None:
    # Each login with the correct password sends one code; the 6th within an
    # hour is throttled (429).
    last = None
    for _ in range(6):
        last = await app_client.post(
            "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
        )
    assert last is not None and last.status_code == 429


@pytest.mark.asyncio
async def test_me_requires_auth(app_client: httpx.AsyncClient, owner: str) -> None:
    resp = await app_client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rate_limit_lockout(app_client: httpx.AsyncClient, owner: str) -> None:
    for _ in range(5):
        r = await app_client.post("/api/auth/login", json={"email": OWNER_EMAIL, "password": "bad"})
        assert r.status_code == 401
    locked = await app_client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert locked.status_code == 429


@pytest.mark.asyncio
async def test_failed_otp_counts_toward_lockout(app_client: httpx.AsyncClient, owner: str) -> None:
    # Four bad passwords + one failed OTP = five failures → next login locked.
    for _ in range(4):
        r = await app_client.post("/api/auth/login", json={"email": OWNER_EMAIL, "password": "bad"})
        assert r.status_code == 401
    otp_token = await _login_to_otp_token(app_client)
    bad_otp = await app_client.post(
        "/api/auth/otp/verify",
        json={"code": "000000"},
        headers={"Authorization": f"Bearer {otp_token}"},
    )
    assert bad_otp.status_code == 401
    locked = await app_client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert locked.status_code == 429


@pytest.mark.asyncio
async def test_existing_otp_challenge_is_blocked_by_aggregate_lockout(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    otp_token = await _login_to_otp_token(app_client)
    code = current_otp()
    for _ in range(5):
        failed = await app_client.post(
            "/api/auth/login", json={"email": OWNER_EMAIL, "password": "bad"}
        )
        assert failed.status_code == 401

    blocked = await app_client.post(
        "/api/auth/otp/verify",
        json={"code": code},
        headers={"Authorization": f"Bearer {otp_token}"},
    )
    assert blocked.status_code == 429
    assert "access_token" not in blocked.json()

    resend = await app_client.post(
        "/api/auth/otp/resend",
        headers={"Authorization": f"Bearer {otp_token}"},
    )
    assert resend.status_code == 429


@pytest.mark.asyncio
async def test_parallel_password_failures_cannot_race_past_lockout(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    async def fail_login() -> httpx.Response:
        return await app_client.post(
            "/api/auth/login", json={"email": OWNER_EMAIL, "password": "bad"}
        )

    results = await asyncio.gather(*(fail_login() for _ in range(6)))
    statuses = [result.status_code for result in results]
    assert statuses.count(401) == 5
    assert statuses.count(429) == 1


@pytest.mark.asyncio
async def test_logout_revokes_session(app_client: httpx.AsyncClient, owner: str) -> None:
    headers = await auth_headers(app_client)
    assert (await app_client.get("/api/auth/me", headers=headers)).status_code == 200
    assert (await app_client.post("/api/auth/logout", headers=headers)).status_code == 200
    assert (await app_client.get("/api/auth/me", headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_refresh_issues_new_access(app_client: httpx.AsyncClient, owner: str) -> None:
    _, refresh = await complete_login(app_client)
    resp = await app_client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    new_access = resp.json()["access_token"]
    rotated_refresh = resp.json()["refresh_token"]
    assert rotated_refresh != refresh
    me = await app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200

    replay = await app_client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert replay.status_code == 401

    # Reuse of an already-rotated token is evidence that the token family was
    # stolen. The entire server-side session is revoked, including the winner's
    # access and refresh tokens.
    next_refresh = await app_client.post(
        "/api/auth/refresh", json={"refresh_token": rotated_refresh}
    )
    assert next_refresh.status_code == 401
    assert (
        await app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    ).status_code == 401


@pytest.mark.asyncio
async def test_parallel_refresh_replay_allows_exactly_one_rotation(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    _, refresh = await complete_login(app_client)

    async def rotate() -> httpx.Response:
        return await app_client.post("/api/auth/refresh", json={"refresh_token": refresh})

    first, second = await asyncio.gather(rotate(), rotate())
    assert sorted([first.status_code, second.status_code]) == [200, 401]
    winner = first if first.status_code == 200 else second
    assert (
        await app_client.post(
            "/api/auth/refresh",
            json={"refresh_token": winner.json()["refresh_token"]},
        )
    ).status_code == 401
    assert (
        await app_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {winner.json()['access_token']}"},
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_revoke_others_keeps_current(app_client: httpx.AsyncClient, owner: str) -> None:
    from app.db.models import Event
    from app.db.session import get_sessionmaker
    from sqlalchemy import select

    access_a, _ = await complete_login(app_client)
    access_b, _ = await complete_login(app_client)
    resp = await app_client.post(
        "/api/auth/sessions/revoke-others", headers={"Authorization": f"Bearer {access_b}"}
    )
    assert resp.status_code == 200
    assert (
        await app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_b}"})
    ).status_code == 200
    assert (
        await app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_a}"})
    ).status_code == 401
    async with get_sessionmaker()() as session:
        event = (
            await session.execute(
                select(Event).where(Event.ref == f"sessions_revoked:{OWNER_EMAIL}")
            )
        ).scalar_one()
        assert event.payload_json["revoked"] == 1


@pytest.mark.asyncio
async def test_dev_code_endpoint_gated(app_client: httpx.AsyncClient, owner: str) -> None:
    # Test mode is on in the suite, so the gated endpoint is reachable and returns
    # the exact login challenge code when given its pending token. The email
    # fallback remains available for manual test-stack inspection.
    otp_token = await _login_to_otp_token(app_client)
    exact = await app_client.get(
        "/api/auth/otp/dev-code",
        headers={"Authorization": f"Bearer {otp_token}"},
    )
    assert exact.status_code == 200
    assert exact.json()["code"] == current_otp()

    resp = await app_client.get("/api/auth/otp/dev-code", params={"email": OWNER_EMAIL})
    assert resp.status_code == 200
    assert resp.json()["code"] == current_otp()
