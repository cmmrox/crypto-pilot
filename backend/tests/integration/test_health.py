"""Integration test for /health against a real database (QA-0)."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_health_ok(app_client: httpx.AsyncClient) -> None:
    resp = await app_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["version"]


@pytest.mark.asyncio
async def test_health_no_secrets_leaked(app_client: httpx.AsyncClient) -> None:
    resp = await app_client.get("/health")
    text = resp.text.lower()
    for forbidden in ("secret", "master_key", "password", "jwt"):
        assert forbidden not in text
