"""Unit tests for the sensitive-data log scrubber (QA-0, LOGGING_GUIDELINES.md)."""

from __future__ import annotations

import logging

from app.core.logging import _scrub_sensitive, configure_logging


def test_masks_known_sensitive_keys() -> None:
    out = _scrub_sensitive(
        None,
        "info",
        {
            "event": "order_placed",
            "api_key": "AKIAsecret",
            "api_secret": "supersecret",
            "password": "hunter2",
            "jwt_secret": "jwt",
            "totp_secret": "totp",
            "otp": "123456",
            "otp_code": "654321",
            "otp_token": "signed-token",
            "code_hash": "deadbeefhash",
            "phone": "94711234567",
            "signature": "deadbeef",
            "side": "SHORT",
        },
    )
    assert out["api_key"] == "***"
    assert out["api_secret"] == "***"
    assert out["password"] == "***"
    assert out["jwt_secret"] == "***"
    assert out["totp_secret"] == "***"
    assert out["otp"] == "***"
    assert out["otp_code"] == "***"
    assert out["otp_token"] == "***"
    assert out["code_hash"] == "***"
    assert out["phone"] == "***"
    assert out["signature"] == "***"
    # Non-sensitive fields are untouched
    assert out["side"] == "SHORT"
    assert out["event"] == "order_placed"


def test_case_insensitive_key_match() -> None:
    out = _scrub_sensitive(None, "info", {"API_KEY": "x", "Authorization": "Bearer y"})
    assert out["API_KEY"] == "***"
    assert out["Authorization"] == "***"


def test_no_sensitive_keys_passthrough() -> None:
    payload = {"event": "tick", "candle_close": "2026-07-17T20:00:00Z", "close": "64821.63"}
    assert _scrub_sensitive(None, "info", dict(payload)) == payload


def test_nested_otp_payload_and_message_are_scrubbed() -> None:
    out = _scrub_sensitive(
        None,
        "info",
        {
            "event": "provider_response",
            "payload": {"verification_code": "123456"},
            "detail": "OTP: 654321 was rejected",
        },
    )
    assert out["payload"]["verification_code"] == "***"
    assert out["detail"] == "OTP *** was rejected"


def test_generic_provider_detail_scrubs_phone_and_credentials() -> None:
    out = _scrub_sensitive(
        None,
        "error",
        {
            "detail": (
                "provider rejected api_key=super-secret "
                "to +94711234567 token:abc123 "
                "https://exchange.test/order?signature=deadbeef"
            )
        },
    )
    assert "super-secret" not in out["detail"]
    assert "94711234567" not in out["detail"]
    assert "abc123" not in out["detail"]
    assert "deadbeef" not in out["detail"]


def test_transport_loggers_cannot_emit_signed_request_urls_at_info() -> None:
    configure_logging()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
