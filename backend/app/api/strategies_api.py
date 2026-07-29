"""Strategy library API: list registered plugins with their validated manifest."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.db.session import get_session
from app.services import strategies as strat_svc
from app.services.settings_store import get_settings_row

router = APIRouter(prefix="/api/strategies", tags=["strategies"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class StrategyOut(BaseModel):
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
    capabilities: list[str]
    params: dict[str, float]
    parity_verified: bool
    validation_method: str
    validation_reference: str
    summary: str
    description: str
    entries: list[str]
    exits: list[str]
    risk_controls: list[str]
    caveats: list[str]
    risk: dict[str, str]
    active: bool


@router.get("", response_model=list[StrategyOut])
async def list_strategies(_current: CurrentUserDep, session: SessionDep) -> list[StrategyOut]:
    """Return registered strategies with their manifest and the active flag."""
    active = strat_svc.resolve((await get_settings_row(session)).active_strategy).name
    out = []
    for info in strat_svc.list_registered():
        out.append(
            StrategyOut(
                name=info.name,
                display_name=info.display_name,
                validated_release=info.validated_release,
                contract_version=info.contract_version,
                direction=info.direction,
                symbol=info.symbol,
                interval=info.interval,
                decision_point=info.decision_point,
                warmup_bars=info.warmup_bars,
                history_bars=info.history_bars,
                capabilities=list(info.capabilities),
                params=info.params,
                parity_verified=info.parity_verified,
                validation_method=info.validation_method,
                validation_reference=info.validation_reference,
                summary=info.summary,
                description=info.description,
                entries=list(info.entries),
                exits=list(info.exits),
                risk_controls=list(info.risk_controls),
                caveats=list(info.caveats),
                risk={
                    "long_risk_pct": str(info.long_risk_pct),
                    "leverage_cap": str(info.leverage_cap),
                    "long_monthly_loss_cap": str(info.long_monthly_loss_cap),
                    "short_monthly_loss_cap": str(info.short_monthly_loss_cap),
                    "short_resize_drift": str(info.short_resize_drift),
                },
                active=info.name == active,
            )
        )
    return out
