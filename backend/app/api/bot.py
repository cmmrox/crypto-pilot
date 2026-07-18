"""Bot lifecycle API: start / stop / stop-and-close / safe-mode / status."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.bot.service import bot_service
from app.db.session import get_session
from app.services import execution_service as exec_svc

router = APIRouter(prefix="/api/bot", tags=["bot"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class BotStatusOut(BaseModel):
    status: str
    environment: str
    strategy: str
    run_id: int | None
    started_at: str | None
    safe_mode_reason: str | None


class MessageOut(BaseModel):
    message: str


@router.get("/status", response_model=BotStatusOut)
async def bot_status(current: CurrentUserDep, session: SessionDep) -> BotStatusOut:
    snap = await bot_service.status(session)
    return BotStatusOut(
        status=snap.status.value,
        environment=snap.environment,
        strategy=snap.strategy,
        run_id=snap.run_id,
        started_at=snap.started_at.isoformat() if snap.started_at else None,
        safe_mode_reason=snap.safe_mode_reason,
    )


@router.post("/start", response_model=MessageOut)
async def start_bot(current: CurrentUserDep, session: SessionDep) -> MessageOut:
    try:
        async with exec_svc.execution_context(session) as ctx:
            run = await bot_service.start(session, ctx.exchange, by=current.user.email)
        return MessageOut(message=f"bot started (run {run.id})")
    except exec_svc.NotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/stop", response_model=MessageOut)
async def stop_bot(current: CurrentUserDep, session: SessionDep) -> MessageOut:
    await bot_service.stop(session, reason="user")
    return MessageOut(message="bot stopped; position left as-is")


@router.post("/stop-close", response_model=MessageOut)
async def stop_and_close(current: CurrentUserDep, session: SessionDep) -> MessageOut:
    try:
        async with exec_svc.execution_context(session) as ctx:
            await bot_service.stop_and_close(session, ctx.exchange, ctx.orders)
        return MessageOut(message="position flattened; bot stopped")
    except exec_svc.NotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/safe-mode", response_model=MessageOut)
async def safe_mode(current: CurrentUserDep, session: SessionDep) -> MessageOut:
    await bot_service.enter_safe_mode(session, reason="manual")
    return MessageOut(message="safe mode enabled; new entries blocked")
