"""Static coverage audit for backtest-critical behavior in the live bot.

This deliberately audits the executable bot path rather than the vectorized
research/parity engine.  A profitable replay is not deployable evidence unless
the live path can represent and persist the same decisions.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REQUIRED_INTENTS = {
    "EnterLong",
    "EnterShort",
    "ResizeShort",
    "MoveStop",
    "TakePartial",
    "ExitAll",
    "Halt",
}


@dataclass(frozen=True)
class LivePathAudit:
    handled_intents: tuple[str, ...]
    missing_intents: tuple[str, ...]
    breaker_state_connected: bool
    long_trade_state_connected: bool
    validated_trailing_high_connected: bool
    specific_order_management_available: bool
    fill_sync_available: bool
    flatten_closes_trade_record: bool
    safe_mode_manages_open_positions: bool
    next_open_execution_available: bool
    passed: bool


def audit(repo_root: Path) -> LivePathAudit:
    bot_path = repo_root / "backend" / "app" / "bot" / "service.py"
    ingest_path = repo_root / "backend" / "app" / "bot" / "ingest.py"
    orders_path = repo_root / "backend" / "app" / "execution" / "orders.py"
    exchange_path = repo_root / "backend" / "app" / "execution" / "exchange.py"
    sync_path = repo_root / "backend" / "app" / "execution" / "trade_sync.py"
    strategy_path = (
        repo_root / "backend" / "app" / "strategies" / "plugins" / "trend_rider_v6_4h.py"
    )
    bot_source = bot_path.read_text(encoding="utf-8")
    ingest_source = ingest_path.read_text(encoding="utf-8")
    orders_source = orders_path.read_text(encoding="utf-8")
    exchange_source = exchange_path.read_text(encoding="utf-8")
    sync_source = sync_path.read_text(encoding="utf-8")
    strategy_source = strategy_path.read_text(encoding="utf-8")
    tree = ast.parse(bot_source)
    handled: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "isinstance":
            continue
        if len(node.args) < 2:
            continue
        type_node = node.args[1]
        if isinstance(type_node, ast.Name):
            handled.add(type_node.id)
        elif isinstance(type_node, ast.Tuple):
            handled.update(item.id for item in type_node.elts if isinstance(item, ast.Name))
    breaker_connected = (
        "halted_long=" in bot_source
        and "halted_short=" in bot_source
        and "evaluate_breaker(" in bot_source
        and "_breaker_event_exists(" in bot_source
        and 'ref=f"breaker:{book}:{month}"' in bot_source
    )
    long_state_connected = (
        "long_stop=" in bot_source and "tp1_done=" in bot_source and "highest_high=" in bot_source
    )
    validated_trailing_high = (
        "state.highest_high" in strategy_source and "current close proxy" not in strategy_source
    )
    specific_order_management = "cancel_order(" in exchange_source and (
        "move_long_stop(" in orders_source
        and "place_stop_market(" in orders_source
        and "cancel_order(" in orders_source
    )
    fill_sync = (
        "get_order(" in exchange_source
        and "get_order_fills(" in exchange_source
        and "sync_open_trade(" in bot_source
        and "realized_pnl" in sync_source
        and "fees" in sync_source
    )
    flatten_source = _function_source(orders_source, "flatten")
    flatten_closes_trade = (
        "closed_at" in flatten_source
        and "exit_px" in flatten_source
        and "realized_pnl" in flatten_source
    )
    evaluate_source = _function_source(bot_source, "evaluate_once")
    safe_mode_manages = not (
        'run.stop_reason == "safe_mode"' in evaluate_source and "return []" in evaluate_source
    )
    next_open_execution = (
        'reason == "candle_close"' in ingest_source
        and "_drive_bot(session, allow_new_entries=True)" in ingest_source
        and "get_mark_price(" in bot_source
    )
    relevant = handled & REQUIRED_INTENTS
    missing = REQUIRED_INTENTS - relevant
    checks = (
        not missing,
        breaker_connected,
        long_state_connected,
        validated_trailing_high,
        specific_order_management,
        fill_sync,
        flatten_closes_trade,
        safe_mode_manages,
        next_open_execution,
    )
    return LivePathAudit(
        handled_intents=tuple(sorted(relevant)),
        missing_intents=tuple(sorted(missing)),
        breaker_state_connected=breaker_connected,
        long_trade_state_connected=long_state_connected,
        validated_trailing_high_connected=validated_trailing_high,
        specific_order_management_available=specific_order_management,
        fill_sync_available=fill_sync,
        flatten_closes_trade_record=flatten_closes_trade,
        safe_mode_manages_open_positions=safe_mode_manages,
        next_open_execution_available=next_open_execution,
        passed=all(checks),
    )


def _function_source(source: str, name: str) -> str:
    """Return one function's source, or an empty string when it is absent."""
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
            end = node.end_lineno or node.lineno
            return "\n".join(lines[node.lineno - 1 : end])
    return ""
