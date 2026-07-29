"""Operations API: kill switch and guarded execution self-check.

The kill switch cancels all orders and flattens all positions on the active
environment. The self-check places a minimum-size round-trip and always cleans up.
LIVE requires the release gates plus an explicit typed confirmation.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.bot.service import bot_service
from app.db.session import get_session
from app.execution.self_check import run_execution_self_check
from app.services import execution_service as exec_svc
from app.services.events import record_event

router = APIRouter(prefix="/api/ops", tags=["ops"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class KillResult(BaseModel):
    ok: bool
    cancelled_orders: int
    detail: str


class SelfCheckResult(BaseModel):
    ok: bool
    filled_qty: str
    entry_price: str
    reconciled: bool
    flattened: bool
    detail: str


class SelfCheckIn(BaseModel):
    side: str = Field(default="LONG", pattern="^(LONG|SHORT)$")
    confirm: str | None = None


@router.post("/kill", response_model=KillResult)
async def kill_switch(current: CurrentUserDep, session: SessionDep) -> KillResult:
    """Cancel all orders and flatten all positions on the active environment."""
    try:
        async with exec_svc.execution_context(session) as ctx:
            cancelled = await bot_service.kill(session, ctx.orders)
        return KillResult(ok=True, cancelled_orders=cancelled, detail="flattened and stopped")
    except exec_svc.NotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/self-check-round-trip", response_model=SelfCheckResult)
async def self_check(
    current: CurrentUserDep,
    session: SessionDep,
    body: SelfCheckIn | None = None,
) -> SelfCheckResult:
    """Place a guarded minimum-size round-trip and finish flat/order-free."""
    try:
        async with exec_svc.execution_context(session) as ctx:
            request = body or SelfCheckIn()
            if ctx.environment == "LIVE":
                if request.confirm != "LIVE-DUST":
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail="LIVE self-check requires typing LIVE-DUST to confirm.",
                    )
                await exec_svc.require_live_ready(session, require_flat=True)
            symbol = ctx.market.symbol
            result = await run_execution_self_check(
                ctx.exchange,
                symbol=symbol,
                side=request.side,
            )
            await record_event(
                session,
                level="INFO",
                category="system",
                message=f"{ctx.environment} {request.side} execution self-check completed",
                ref="self_check",
                payload={
                    "environment": ctx.environment,
                    "side": request.side,
                    "qty": str(result.filled_qty),
                    "entry": str(result.entry_price),
                    "reconciled": result.reconciled,
                    "protective_stop_verified": result.protective_stop_verified,
                    "take_profit_verified": result.take_profit_verified,
                    "individual_cancel_verified": result.individual_cancel_verified,
                    "flattened": result.flattened,
                    "zero_open_orders": result.zero_open_orders,
                    "by": current.user.email,
                },
            )
            return SelfCheckResult(
                ok=True,
                filled_qty=str(result.filled_qty),
                entry_price=str(result.entry_price),
                reconciled=result.reconciled,
                flattened=result.flattened,
                detail="round-trip ok",
            )
    except exec_svc.NotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except exec_svc.LiveTradingBlockedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
