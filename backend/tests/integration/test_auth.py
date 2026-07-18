"""Integration tests for the authentication flow (QA-1)."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import OWNER_EMAIL, OWNER_PASSWORD, current_totp


async def _login_to_totp_token(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["totp_token"]


async def _full_login(client: httpx.AsyncClient, secret: str) -> tuple[str, str]:
    totp_token = await _login_to_totp_token(client)
    resp = await client.post(
        "/api/auth/totp",
        json={"code": current_totp(secret)},
        headers={"Authorization": f"Bearer {totp_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["access_token"], body["refresh_token"]


@pytest.mark.asyncio
async def test_happy_path_login(app_client: httpx.AsyncClient, owner: str) -> None:
    access, refresh = await _full_login(app_client, owner)
    me = await app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["email"] == OWNER_EMAIL
    assert refresh


@pytest.mark.asyncio
async def test_wrong_password_rejected(app_client: httpx.AsyncClient, owner: str) -> None:
    resp = await app_client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": "wrong-password"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_totp_rejected(app_client: httpx.AsyncClient, owner: str) -> None:
    totp_token = await _login_to_totp_token(app_client)
    resp = await app_client.post(
        "/api/auth/totp",
        json={"code": "000000"},
        headers={"Authorization": f"Bearer {totp_token}"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(app_client: httpx.AsyncClient, owner: str) -> None:
    resp = await app_client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rate_limit_lockout(app_client: httpx.AsyncClient, owner: str) -> None:
    # 5 failures triggers lockout on the 6th attempt (429).
    for _ in range(5):
        r = await app_client.post(
            "/api/auth/login", json={"email": OWNER_EMAIL, "password": "bad"}
        )
        assert r.status_code == 401
    locked = await app_client.post(
        "/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert locked.status_code == 429


@pytest.mark.asyncio
async def test_failure_counter_resets_after_success(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    # 4 failures (below the 5 threshold), then a successful login must reset the counter.
    for _ in range(4):
        r = await app_client.post(
            "/api/auth/login", json={"email": OWNER_EMAIL, "password": "bad"}
        )
        assert r.status_code == 401
    await _full_login(app_client, owner)  # success resets the window
    # 4 more failures should still be allowed (counter reset), not locked.
    for _ in range(4):
        r = await app_client.post(
            "/api/auth/login", json={"email": OWNER_EMAIL, "password": "bad"}
        )
        assert r.status_code == 401  # 401, not 429 — proves the reset


@pytest.mark.asyncio
async def test_logout_revokes_session(app_client: httpx.AsyncClient, owner: str) -> None:
    access, _ = await _full_login(app_client, owner)
    headers = {"Authorization": f"Bearer {access}"}
    assert (await app_client.get("/api/auth/me", headers=headers)).status_code == 200
    assert (await app_client.post("/api/auth/logout", headers=headers)).status_code == 200
    # Token is syntactically valid but the session is revoked.
    assert (await app_client.get("/api/auth/me", headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_refresh_issues_new_access(app_client: httpx.AsyncClient, owner: str) -> None:
    _, refresh = await _full_login(app_client, owner)
    resp = await app_client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    new_access = resp.json()["access_token"]
    me = await app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_revoke_others_keeps_current(app_client: httpx.AsyncClient, owner: str) -> None:
    access_a, _ = await _full_login(app_client, owner)
    access_b, _ = await _full_login(app_client, owner)
    # Session B revokes all others (including A).
    resp = await app_client.post(
        "/api/auth/sessions/revoke-others", headers={"Authorization": f"Bearer {access_b}"}
    )
    assert resp.status_code == 200
    # B still works, A is dead.
    assert (
        await app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_b}"})
    ).status_code == 200
    assert (
        await app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_a}"})
    ).status_code == 401


@pytest.mark.asyncio
async def test_reused_totp_pending_after_login_still_needs_valid_code(
    app_client: httpx.AsyncClient, owner: str
) -> None:
    # A totp_pending token cannot be used as an access token.
    totp_token = await _login_to_totp_token(app_client)
    resp = await app_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {totp_token}"}
    )
    assert resp.status_code == 401
