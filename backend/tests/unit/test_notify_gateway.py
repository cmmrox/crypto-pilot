"""Unit tests for the notify.lk SMS gateway.

The gateway's send() is a fire-and-log call on the trading path: it MUST never
raise, because an exception would propagate through notify() and roll back a
trade whose exchange order has already filled (exchange/DB divergence).
"""

from __future__ import annotations

import httpx
import pytest
from app.notifier.gateway import NotifyLkGateway


def _gateway_with(handler: object) -> NotifyLkGateway:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport)
    return NotifyLkGateway("uid", "key", "SENDER", client=client)


async def test_send_success_returns_ok() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "success"})

    gw = _gateway_with(handler)
    result = await gw.send("94711234567", "hi")
    assert result.ok is True
    assert result.detail == "delivered"


async def test_send_provider_rejection_is_not_leaked() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        # Provider echoes back submitted fields including the api_key.
        return httpx.Response(200, json={"status": "error", "api_key": "key"})

    gw = _gateway_with(handler)
    result = await gw.send("94711234567", "hi")
    assert result.ok is False
    assert "key" not in result.detail
    assert result.detail == "provider rejected request"


async def test_send_malformed_json_body_does_not_raise() -> None:
    """A body labelled application/json but syntactically broken must degrade
    to a failed result, never a JSONDecodeError escaping the trading path."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"{not-json",
            headers={"content-type": "application/json"},
        )

    gw = _gateway_with(handler)
    result = await gw.send("94711234567", "hi")
    assert result.ok is False
    assert result.detail == "provider response error"


async def test_send_non_object_json_body_does_not_raise() -> None:
    """A JSON array/scalar (no .get) must not raise AttributeError."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["success"])

    gw = _gateway_with(handler)
    result = await gw.send("94711234567", "hi")
    assert result.ok is False


async def test_send_transport_error_returns_failure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    gw = _gateway_with(handler)
    result = await gw.send("94711234567", "hi")
    assert result.ok is False
    assert result.detail == "provider transport error"


async def test_send_non_json_content_type_is_rejected() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="OK", headers={"content-type": "text/plain"})

    gw = _gateway_with(handler)
    result = await gw.send("94711234567", "hi")
    assert result.ok is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
