"""Guarded operational settings: environment switch + active-strategy selection.

Both are refused while the bot is running (BSD FR-01/§7). Switching to LIVE requires
a typed confirmation echoed by the client. All changes are audited.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.bot.service import bot_service
from app.bot.state import BotStatus
from app.core.config import get_settings
from app.db.session import get_session
from app.services import execution_service as exec_svc
from app.services.events import record_event
from app.services.settings_store import get_settings_row
from app.services.strategy_selection import (
    StrategySelectionBlockedError,
    UnknownStrategyError,
    select_active_strategy,
)

router = APIRouter(prefix="/api/settings", tags=["settings-admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class EnvironmentIn(BaseModel):
    environment: str = Field(pattern="^(DEMO|LIVE)$")
    confirm: str | None = None  # must equal "LIVE" when switching to LIVE


class StrategyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    runtime = get_settings()
    if body.environment == "LIVE" and not (
        runtime.live_trading_approved and runtime.live_key_permissions_verified
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=(
                "LIVE is locked until Stage 11 acceptance and Binance key "
                "permissions are independently verified."
            ),
        )
    if body.environment == "LIVE":
        try:
            await exec_svc.require_live_ready(session, require_flat=True)
        except exec_svc.LiveTradingBlockedError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    row = await get_settings_row(session, for_update=True)
    await _require_stopped(session)
    old = row.active_environment
    row.active_environment = body.environment
    await record_event(
        session,
        level="WARN" if body.environment == "LIVE" else "INFO",
        category="security",
        message=f"Environment switched {old} → {body.environment}",
        ref="env_switch",
        payload={"from": old, "to": body.environment, "by": current.user.email},
    )
    await session.commit()
    return MessageOut(message=f"environment set to {body.environment}")


@router.put("/strategy", response_model=MessageOut)
async def switch_strategy(
    body: StrategyIn, current: CurrentUserDep, session: SessionDep
) -> MessageOut:
    try:
        selected = await select_active_strategy(
            session,
            requested_name=body.name,
            actor_email=current.user.email,
        )
    except UnknownStrategyError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="unknown strategy") from None
    except StrategySelectionBlockedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from None
    return MessageOut(message=f"active strategy set to {selected}")
