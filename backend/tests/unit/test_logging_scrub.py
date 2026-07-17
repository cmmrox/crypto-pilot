"""Unit tests for the sensitive-data log scrubber (QA-0, LOGGING_GUIDELINES.md)."""

from __future__ import annotations

from app.core.logging import _scrub_sensitive


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
            "signature": "deadbeef",
            "side": "SHORT",
        },
    )
    assert out["api_key"] == "***"
    assert out["api_secret"] == "***"
    assert out["password"] == "***"
    assert out["jwt_secret"] == "***"
    assert out["totp_secret"] == "***"
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
