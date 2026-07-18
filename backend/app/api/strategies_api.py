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
    validated_release: str
    direction: str
    warmup_bars: int
    params: dict[str, float]
    parity_verified: bool
    active: bool


@router.get("", response_model=list[StrategyOut])
async def list_strategies(_current: CurrentUserDep, session: SessionDep) -> list[StrategyOut]:
    """Return registered strategies with their manifest and the active flag."""
    active = (await get_settings_row(session)).active_strategy
    out = []
    for info in strat_svc.list_registered():
        out.append(
            StrategyOut(
                name=info.name,
                validated_release=info.validated_release,
                direction=info.direction,
                warmup_bars=info.warmup_bars,
                params=info.params,
                parity_verified=info.parity_verified,
                active=info.name == active,
            )
        )
    return out
