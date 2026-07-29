"""Automatic discovery and fail-closed validation of built-in strategies."""

from __future__ import annotations

import importlib
import pkgutil
import re
from collections.abc import Iterable

from app.strategies import plugins
from app.strategies.base import Strategy, get_registered, registered_items

_DISCOVERED = False
_STRATEGY_ID = re.compile(r"^[a-z][a-z0-9_]*_[0-9]+[mhd]$")
_APPROVED_INTERVALS = frozenset({"4h"})


def discover() -> None:
    """Import every built-in strategy module exactly once."""
    global _DISCOVERED
    if _DISCOVERED:
        return
    for module in pkgutil.iter_modules(plugins.__path__, f"{plugins.__name__}."):
        leaf = module.name.rsplit(".", 1)[-1]
        if leaf.startswith("_"):
            continue
        imported = importlib.import_module(module.name)
        plugin = getattr(imported, "PLUGIN", None)
        if plugin is None:
            raise RuntimeError(f"strategy module {module.name} does not export PLUGIN")
        if plugin.manifest.strategy_id != leaf:
            raise RuntimeError(
                f"strategy module {leaf} must match strategy_id {plugin.manifest.strategy_id}"
            )
    _validate_all(strategy for _, strategy in registered_items())
    _DISCOVERED = True


def _validate_all(strategies: Iterable[Strategy]) -> None:
    default_count = 0
    aliases: set[str] = set()
    for strategy in strategies:
        manifest = strategy.manifest
        if manifest.contract_version != 2:
            raise RuntimeError(
                f"{manifest.strategy_id}: unsupported contract {manifest.contract_version}"
            )
        if not _STRATEGY_ID.fullmatch(manifest.strategy_id):
            raise RuntimeError(
                f"{manifest.strategy_id}: expected lowercase name ending in timeframe"
            )
        if not manifest.strategy_id.endswith(f"_{manifest.market.interval}"):
            raise RuntimeError(
                f"{manifest.strategy_id}: filename/id timeframe does not match "
                f"{manifest.market.interval}"
            )
        if manifest.market.interval not in _APPROVED_INTERVALS:
            raise RuntimeError(
                f"{manifest.strategy_id}: interval {manifest.market.interval} is not owner-approved"
            )
        if manifest.market.decision_point != "closed_candle":
            raise RuntimeError(f"{manifest.strategy_id}: decisions must use closed candles")
        if manifest.market.warmup_bars <= 0:
            raise RuntimeError(f"{manifest.strategy_id}: warmup_bars must be positive")
        if manifest.market.history_bars < manifest.market.warmup_bars:
            raise RuntimeError(f"{manifest.strategy_id}: history_bars must cover the warmup")
        if manifest.validation.status != "verified":
            raise RuntimeError(f"{manifest.strategy_id}: release is not verified")
        default_count += int(manifest.packaged_default)
        for alias in manifest.legacy_ids:
            if alias in aliases:
                raise RuntimeError(f"duplicate legacy strategy id: {alias}")
            aliases.add(alias)
    if default_count != 1:
        raise RuntimeError("exactly one packaged default strategy is required")


def get_strategy(name: str) -> Strategy:
    discover()
    return get_registered(name)


def registered_strategies() -> tuple[Strategy, ...]:
    discover()
    return tuple(strategy for _, strategy in registered_items())


def registered_names() -> list[str]:
    return sorted(strategy.manifest.strategy_id for strategy in registered_strategies())


def default_strategy() -> Strategy:
    defaults = [
        strategy for strategy in registered_strategies() if strategy.manifest.packaged_default
    ]
    return defaults[0]


def canonical_strategy_id(name: str) -> str:
    return get_strategy(name).manifest.strategy_id
