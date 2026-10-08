"""SMS templates per event type (BSD §10). Kept ≤320 chars after rendering."""

from __future__ import annotations

from typing import Any

# Event kinds → template. {placeholders} filled from the event payload.
TEMPLATES: dict[str, str] = {
    "trade_opened": "CryptoPilot: {side} opened {qty} BTC @ {price}. {risk_context} ({environment})",
    "short_opened": (
        "CryptoPilot: SHORT sleeve opened {qty} BTC @ {price} "
        "({weight} of equity, vol-scaled). No price stop; covers on regime end."
    ),
    "trade_closed": (
        "CryptoPilot: {side} closed @ {exit} ({reason}). P&L {pnl} net of fees/funding. "
        "Month closed P&L: {month_pnl}. ({environment})"
    ),
    "tp1_filled": (
        "CryptoPilot: {side} TP1 filled {qty} BTC @ {price}. Remaining {remaining} BTC "
        "protected by stop {stop}. ({environment})"
    ),
    "short_resized": (
        "CryptoPilot: SHORT sleeve resized {previous_qty} -> {target_qty} BTC "
        "({weight} of equity, {reason})."
    ),
    "bot_started": (
        "CryptoPilot: bot STARTED on {environment}, strategy {strategy}, equity {equity}."
        "{safe_mode_note}"
    ),
    "bot_stopped": "CryptoPilot: bot STOPPED by {actor}. {position_note}",
    "safe_mode": (
        "CryptoPilot ALERT: SAFE MODE ({reason}). New entries blocked; exchange stops stay "
        "active. Check dashboard."
    ),
    "strategy_halt": "CryptoPilot: strategy halted new entries until {until}.",
    "kill_switch": (
        "CryptoPilot: KILL SWITCH completed. Positions flattened and "
        "{cancelled_orders} resting orders cancelled."
    ),
    "breaker": (
        "CryptoPilot: {book} monthly loss cap hit ({pnl}, {pct} of month-start equity; "
        "cap {cap}). {book} entries halted until the 1st; the other book keeps trading."
    ),
    "error": "CryptoPilot ALERT: {error}. Bot paused — check dashboard.",
    "health": "CryptoPilot ALERT: {error}. Check the VPS and dashboard.",
    "health_recovered": "CryptoPilot: {message}. Confirm the bot state on the dashboard.",
}

# Which event categories map to which SMS kind, and whether they're enabled by default.
DEFAULT_TOGGLES: dict[str, bool] = {
    "trade_opened": True,
    "short_opened": True,
    "trade_closed": True,
    "tp1_filled": True,
    "short_resized": True,
    "bot_started": True,
    "bot_stopped": True,
    "kill_switch": True,
    "safe_mode": True,
    "strategy_halt": True,
    "breaker": True,
    "error": True,
    "health": True,
    "health_recovered": True,
}


def render(kind: str, payload: dict[str, Any]) -> str:
    """Render a template with payload values; missing keys become '—'."""
    template = TEMPLATES.get(kind)
    if template is None:
        raise KeyError(f"unknown SMS template: {kind}")

    class _Default(dict[str, Any]):
        def __missing__(self, key: str) -> str:
            return "—"

    return template.format_map(_Default(payload))[:320]
