"""Integration tests for the guarded 2FA settings flows (QA-9).

Covers enable / disable / change-number, the password re-check, OTP confirmation,
session revocation on sensitive changes, and password-only login once 2FA is off.
"""

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

NEW_PHONE = "94770000000"
SECOND_NEW_PHONE = "94771111111"


async def _start(
    client: httpx.AsyncClient, headers: dict[str, str], body: dict[str, object]
) -> httpx.Response:
    return await client.post("/api/settings/security/2fa/start", json=body, headers=headers)


async def _confirm(
    client: httpx.AsyncClient, headers: dict[str, str], challenge_id: int, code: str
) -> httpx.Response:
    return await client.post(
        "/api/settings/security/2fa/confirm",
        json={"challenge_id": challenge_id, "code": code},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_security_status_reports_enabled(app_client: httpx.AsyncClient, owner: str) -> None:
    headers = await auth_headers(app_client)
    resp = await app_client.get("/api/settings/security", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["twofa_enabled"] is True
    assert body["phone_hint"].endswith("4567")


@pytest.mark.asyncio
async def test_disable_requires_correct_password(app_client: httpx.AsyncClient, owner: str) -> None:
    headers = await auth_headers(app_client)
    resp = await _start(app_client, headers, {"password": "wrong", "action": "disable"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_security_change_password_reauth_is_rate_limited(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    headers = await auth_headers(app_client)
    for _ in range(5):
        response = await _start(app_client, headers, {"password": "wrong", "action": "disable"})
        assert response.status_code == 401
    locked = await _start(
        app_client,
        headers,
        {"password": OWNER_PASSWORD, "action": "disable"},
    )
    assert locked.status_code == 429


@pytest.mark.asyncio
async def test_parallel_security_change_guesses_cannot_race_past_lockout(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    headers = await auth_headers(app_client)

    async def guess() -> httpx.Response:
        return await _start(app_client, headers, {"password": "wrong", "action": "disable"})

    responses = await asyncio.gather(*(guess() for _ in range(6)))
    statuses = [response.status_code for response in responses]
    assert statuses.count(401) == 5
    assert statuses.count(429) == 1


@pytest.mark.asyncio
async def test_disable_requires_valid_otp(app_client: httpx.AsyncClient, owner: str) -> None:
    headers = await auth_headers(app_client)
    start = await _start(app_client, headers, {"password": OWNER_PASSWORD, "action": "disable"})
    assert start.status_code == 200
    challenge_id = start.json()["challenge_id"]
    bad = await _confirm(app_client, headers, challenge_id, "000000")
    assert bad.status_code == 401
    # Still enabled after a failed confirm.
    status = await app_client.get("/api/settings/security", headers=headers)
    assert status.json()["twofa_enabled"] is True


@pytest.mark.asyncio
async def test_disable_then_password_only_login(app_client: httpx.AsyncClient, owner: str) -> None:
    headers = await auth_headers(app_client)
    start = await _start(app_client, headers, {"password": OWNER_PASSWORD, "action": "disable"})
    challenge_id = start.json()["challenge_id"]
    # Disable code goes to the current (owner) number.
    confirm = await _confirm(app_client, headers, challenge_id, current_otp())
    assert confirm.status_code == 200

    # Login now returns tokens directly, no OTP step.
    resp = await app_client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    body = resp.json()
    assert body["mode"] == "tokens"
    assert body["access_token"]
    me = await app_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_change_phone_verifies_new_number_and_revokes_sessions(
    app_client: httpx.AsyncClient,
    owner: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.notifier.gateway import SmsResult
    from app.services import auth as auth_service

    notified: list[str] = []

    async def capture_notice(_config: object, phone: str, _message: str) -> SmsResult:
        notified.append(phone)
        return SmsResult(True, "delivered")

    monkeypatch.setattr(auth_service, "_send_security_notice", capture_notice)
    access_a, _ = await complete_login(app_client)
    access_b, _ = await complete_login(app_client)
    headers_b = {"Authorization": f"Bearer {access_b}"}

    start = await _start(
        app_client,
        headers_b,
        {"password": OWNER_PASSWORD, "action": "change_phone", "new_phone": NEW_PHONE},
    )
    assert start.status_code == 200
    # The code must be sent to the NEW number.
    confirm = await _confirm(
        app_client,
        headers_b,
        start.json()["challenge_id"],
        current_otp(NEW_PHONE),
    )
    assert confirm.status_code == 200

    # Session A (an "other" session) is revoked; B (the actor) survives.
    assert (
        await app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_a}"})
    ).status_code == 401
    assert (await app_client.get("/api/auth/me", headers=headers_b)).status_code == 200

    status = await app_client.get("/api/settings/security", headers=headers_b)
    assert status.json()["phone_hint"].endswith("0000")
    assert notified == ["94711234567"]


@pytest.mark.asyncio
async def test_phone_change_invalidates_pending_disable_challenge(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    headers = await auth_headers(app_client)
    disable = await _start(app_client, headers, {"password": OWNER_PASSWORD, "action": "disable"})
    disable_id = disable.json()["challenge_id"]
    disable_code = current_otp()

    change = await _start(
        app_client,
        headers,
        {
            "password": OWNER_PASSWORD,
            "action": "change_phone",
            "new_phone": NEW_PHONE,
        },
    )
    changed = await _confirm(
        app_client,
        headers,
        change.json()["challenge_id"],
        current_otp(NEW_PHONE),
    )
    assert changed.status_code == 200

    stale = await _confirm(app_client, headers, disable_id, disable_code)
    assert stale.status_code in {400, 401}
    status_response = await app_client.get("/api/settings/security", headers=headers)
    assert status_response.json()["twofa_enabled"] is True


@pytest.mark.asyncio
async def test_parallel_phone_change_confirms_are_serialized(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    headers = await auth_headers(app_client)
    first = await _start(
        app_client,
        headers,
        {
            "password": OWNER_PASSWORD,
            "action": "change_phone",
            "new_phone": NEW_PHONE,
        },
    )
    second = await _start(
        app_client,
        headers,
        {
            "password": OWNER_PASSWORD,
            "action": "change_phone",
            "new_phone": SECOND_NEW_PHONE,
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_code = current_otp(NEW_PHONE)
    second_code = current_otp(SECOND_NEW_PHONE)

    responses = await asyncio.gather(
        _confirm(app_client, headers, first.json()["challenge_id"], first_code),
        _confirm(app_client, headers, second.json()["challenge_id"], second_code),
    )
    statuses = [response.status_code for response in responses]
    assert statuses.count(200) == 1
    assert sum(status in {400, 401} for status in statuses) == 1

    status = await app_client.get("/api/settings/security", headers=headers)
    assert status.status_code == 200
    assert status.json()["phone_hint"][-4:] in {
        NEW_PHONE[-4:],
        SECOND_NEW_PHONE[-4:],
    }


@pytest.mark.asyncio
async def test_phone_format_is_strict_notify_lk_form(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    headers = await auth_headers(app_client)
    for invalid in ["+94770000000", "0770000000", "9477000000", "947700000000"]:
        response = await _start(
            app_client,
            headers,
            {
                "password": OWNER_PASSWORD,
                "action": "change_phone",
                "new_phone": invalid,
            },
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_enable_after_disable(app_client: httpx.AsyncClient, owner: str) -> None:
    headers = await auth_headers(app_client)
    # Disable first.
    start = await _start(app_client, headers, {"password": OWNER_PASSWORD, "action": "disable"})
    await _confirm(app_client, headers, start.json()["challenge_id"], current_otp())

    # Re-enable with a fresh number (password-only login still works for headers).
    resp = await app_client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    start = await _start(
        app_client,
        headers,
        {"password": OWNER_PASSWORD, "action": "enable", "new_phone": NEW_PHONE},
    )
    assert start.status_code == 200
    confirm = await _confirm(
        app_client,
        headers,
        start.json()["challenge_id"],
        current_otp(NEW_PHONE),
    )
    assert confirm.status_code == 200

    status = await app_client.get("/api/settings/security", headers=headers)
    assert status.json()["twofa_enabled"] is True
    assert status.json()["phone_hint"].endswith("0000")


@pytest.mark.asyncio
async def test_enable_requires_phone(app_client: httpx.AsyncClient, owner: str) -> None:
    # Owner already has 2FA on; enabling again is rejected, but also prove the
    # missing-phone guard on a disabled account.
    headers = await auth_headers(app_client)
    start = await _start(app_client, headers, {"password": OWNER_PASSWORD, "action": "disable"})
    await _confirm(app_client, headers, start.json()["challenge_id"], current_otp())
    resp = await app_client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    bad = await _start(app_client, headers, {"password": OWNER_PASSWORD, "action": "enable"})
    assert bad.status_code == 400
