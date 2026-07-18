"""Guarded operational settings: environment switch + active-strategy selection.

Both are refused while the bot is running (BSD FR-01/§7). Switching to LIVE requires
a typed confirmation echoed by the client. All changes are audited.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.bot.service import bot_service
from app.bot.state import BotStatus
from app.db.session import get_session
from app.services import strategies as strat_svc
from app.services.events import record_event
from app.services.settings_store import get_settings_row

router = APIRouter(prefix="/api/settings", tags=["settings-admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class EnvironmentIn(BaseModel):
    environment: str = Field(pattern="^(DEMO|LIVE)$")
    confirm: str | None = None  # must equal "LIVE" when switching to LIVE


class StrategyIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class MessageOut(BaseModel):
    message: str


async def _require_stopped(session: AsyncSession) -> None:
    snap = await bot_service.status(session)
    if snap.status != BotStatus.STOPPED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Stop the bot before changing environment or strategy.",
        )


@router.put("/environment", response_model=MessageOut)
async def switch_environment(
    body: EnvironmentIn, current: CurrentUserDep, session: SessionDep
) -> MessageOut:
    await _require_stopped(session)
    if body.environment == "LIVE" and body.confirm != "LIVE":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Switching to LIVE requires typing LIVE to confirm.",
        )
    row = await get_settings_row(session)
    old = row.active_environment
    row.active_environment = body.environment
    await record_event(
        session, level="WARN" if body.environment == "LIVE" else "INFO", category="security",
        message=f"Environment switched {old} → {body.environment}",
        ref="env_switch", payload={"from": old, "to": body.environment, "by": current.user.email},
    )
    return MessageOut(message=f"environment set to {body.environment}")


@router.put("/strategy", response_model=MessageOut)
async def switch_strategy(
    body: StrategyIn, current: CurrentUserDep, session: SessionDep
) -> MessageOut:
    await _require_stopped(session)
    if body.name not in {s.name for s in strat_svc.list_registered()}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="unknown strategy")
    row = await get_settings_row(session)
    old = row.active_strategy
    row.active_strategy = body.name
    await record_event(
        session, level="INFO", category="strategy",
        message=f"Active strategy switched {old} → {body.name}",
        ref="strategy_switch", payload={"from": old, "to": body.name, "by": current.user.email},
    )
    return MessageOut(message=f"active strategy set to {body.name}")
