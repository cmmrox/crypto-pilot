"""Unit tests for SMS template rendering (QA-7)."""

from __future__ import annotations

import pytest
from app.notifier.templates import render


def test_trade_opened_renders_values() -> None:
    msg = render("trade_opened", {"side": "LONG", "qty": "0.01", "price": "65000",
                                  "risk_context": "Stop 63k", "environment": "DEMO"})
    assert "LONG opened 0.01 BTC @ 65000" in msg
    assert "(DEMO)" in msg


def test_short_opened_mentions_no_stop() -> None:
    msg = render("short_opened", {"qty": "0.008", "price": "63000", "weight": "48%"})
    assert "No price stop" in msg


def test_missing_placeholders_become_dash() -> None:
    msg = render("trade_closed", {"side": "LONG"})
    assert "—" in msg  # pnl/reason/month_pnl missing


def test_message_capped_at_320() -> None:
    msg = render("error", {"error": "x" * 500})
    assert len(msg) <= 320


def test_unknown_template_raises() -> None:
    with pytest.raises(KeyError):
        render("nope", {})
