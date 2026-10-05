"""Immutable strategy metadata consumed by the runtime and owner console.

The manifest is strategy-owned configuration. It describes what data a strategy
needs and how the validated release behaves, while the application continues to
own clocks, I/O, sizing calculations, reconciliation, and order placement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class MarketSpec:
    """The one closed-candle feed required by a strategy release."""

    symbol: str
    interval: str
    decision_point: str
    warmup_bars: int
    history_bars: int


@dataclass(frozen=True)
class RiskSpec:
    """Read-only policy values enforced by the generic risk engine."""

    long_risk_pct: Decimal
    leverage_cap: Decimal
    long_monthly_loss_cap: Decimal
    short_monthly_loss_cap: Decimal
    short_resize_drift: Decimal


@dataclass(frozen=True)
class StrategyEducation:
    """Safe, plain-language content rendered without strategy-specific UI code."""

    summary: str
    description: str
    entries: tuple[str, ...]
    exits: tuple[str, ...]
    risk_controls: tuple[str, ...]
    caveats: tuple[str, ...]


@dataclass(frozen=True)
class ValidationEvidence:
    """The checked-in evidence expected before a release may be activated."""

    method: str
    status: str
    reference: str


@dataclass(frozen=True)
class ExecutionSpec:
    """Release-owned execution rules; defaults preserve established releases."""

    anchor_to_fill: bool = False
    partial_round_down: bool = False
    breakeven_on_tp_fill: bool = False
    stop_working_type: Literal["MARK_PRICE", "CONTRACT_PRICE"] = "MARK_PRICE"


@dataclass(frozen=True)
class StrategyManifest:
    """The complete application-facing identity of one strategy release."""

    contract_version: int
    strategy_id: str
    display_name: str
    release: str
    packaged_default: bool
    direction: str
    capabilities: tuple[str, ...]
    market: MarketSpec
    risk: RiskSpec
    education: StrategyEducation
    validation: ValidationEvidence
    legacy_ids: tuple[str, ...] = ()
    execution: ExecutionSpec = field(default_factory=ExecutionSpec)
