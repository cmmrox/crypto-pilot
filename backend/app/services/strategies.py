"""Application-facing view of the strategy-owned plugin manifests."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.strategies import get_strategy, registered_strategies


@dataclass(frozen=True)
class StrategyInfo:
    name: str
    display_name: str
    validated_release: str
    contract_version: int
    direction: str
    symbol: str
    interval: str
    decision_point: str
    warmup_bars: int
    history_bars: int
    capabilities: tuple[str, ...]
    params: dict[str, float]
    parity_verified: bool
    validation_method: str
    validation_reference: str
    summary: str
    description: str
    entries: tuple[str, ...]
    exits: tuple[str, ...]
    risk_controls: tuple[str, ...]
    caveats: tuple[str, ...]
    long_risk_pct: Decimal
    leverage_cap: Decimal
    long_monthly_loss_cap: Decimal
    short_monthly_loss_cap: Decimal
    short_resize_drift: Decimal


def list_registered() -> list[StrategyInfo]:
    infos: list[StrategyInfo] = []
    for strategy in registered_strategies():
        manifest = strategy.manifest
        infos.append(
            StrategyInfo(
                name=manifest.strategy_id,
                display_name=manifest.display_name,
                validated_release=manifest.release,
                contract_version=manifest.contract_version,
                direction=manifest.direction,
                symbol=manifest.market.symbol,
                interval=manifest.market.interval,
                decision_point=manifest.market.decision_point,
                warmup_bars=manifest.market.warmup_bars,
                history_bars=manifest.market.history_bars,
                capabilities=manifest.capabilities,
                params=dict(strategy.params),
                parity_verified=manifest.validation.status == "verified",
                validation_method=manifest.validation.method,
                validation_reference=manifest.validation.reference,
                summary=manifest.education.summary,
                description=manifest.education.description,
                entries=manifest.education.entries,
                exits=manifest.education.exits,
                risk_controls=manifest.education.risk_controls,
                caveats=manifest.education.caveats,
                long_risk_pct=manifest.risk.long_risk_pct,
                leverage_cap=manifest.risk.leverage_cap,
                long_monthly_loss_cap=manifest.risk.long_monthly_loss_cap,
                short_monthly_loss_cap=manifest.risk.short_monthly_loss_cap,
                short_resize_drift=manifest.risk.short_resize_drift,
            )
        )
    return infos


def resolve(name: str) -> StrategyInfo:
    canonical = get_strategy(name).manifest.strategy_id
    return next(info for info in list_registered() if info.name == canonical)
