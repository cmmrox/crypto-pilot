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
    "trade_closed": "CryptoPilot: {side} closed {pnl} ({reason}). Month: {month_pnl}.",
    "short_resized": "CryptoPilot: SHORT resized to {weight} of equity ({reason}).",
    "bot_started": "CryptoPilot: bot STARTED on {environment}, strategy {strategy}, equity {equity}.",
    "bot_stopped": "CryptoPilot: bot STOPPED by {actor}. Open position left with its exchange stops.",
    "kill_switch": (
        "CryptoPilot: KILL SWITCH completed. Positions flattened and "
        "{cancelled_orders} resting orders cancelled."
    ),
    "breaker": "CryptoPilot: monthly loss cap hit (-4%). All closed. Halted until the 1st.",
    "error": "CryptoPilot ALERT: {error}. Bot paused — check dashboard.",
}

# Which event categories map to which SMS kind, and whether they're enabled by default.
DEFAULT_TOGGLES: dict[str, bool] = {
    "trade_opened": True,
    "short_opened": True,
    "trade_closed": True,
    "short_resized": True,
    "bot_started": True,
    "bot_stopped": True,
    "kill_switch": True,
    "breaker": True,
    "error": True,
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
