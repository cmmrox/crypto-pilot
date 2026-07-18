"""News + Codex device-code auth API (isolated module — no trading access)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.db.session import get_session
from app.news import service as news_svc
from app.news.codex_auth import codex_auth
from app.news.collector import MACRO_CALENDAR

router = APIRouter(prefix="/api/news", tags=["news"])
codex_router = APIRouter(prefix="/api/settings/codex", tags=["codex"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class BriefingOut(BaseModel):
    briefing_date: str | None
    model: str | None
    sentiment: str | None
    bullets: list[dict[str, str]]
    generated_at: str | None
    macro_calendar: list[dict[str, str]]
    isolation_notice: str


class ArchiveItem(BaseModel):
    briefing_date: str
    sentiment: str | None
    model: str | None


@router.get("/latest", response_model=BriefingOut)
async def latest(_current: CurrentUserDep, session: SessionDep) -> BriefingOut:
    b = await news_svc.latest_briefing(session)
    return BriefingOut(
        briefing_date=b.briefing_date.isoformat() if b else None,
        model=b.model if b else None,
        sentiment=b.sentiment if b else None,
        bullets=b.bullets if b else [],
        generated_at=b.generated_at.isoformat() if b else None,
        macro_calendar=MACRO_CALENDAR,
        isolation_notice=(
            "The news agent is read-only context for the human. It has no exchange keys, "
            "cannot gate signals, and never feeds the strategy."
        ),
    )


@router.get("/archive", response_model=list[ArchiveItem])
async def archive(_current: CurrentUserDep, session: SessionDep) -> list[ArchiveItem]:
    rows = await news_svc.archive(session)
    return [
        ArchiveItem(briefing_date=r.briefing_date.isoformat(), sentiment=r.sentiment, model=r.model)
        for r in rows
    ]


class RefreshOut(BaseModel):
    ok: bool
    detail: str


@router.post("/refresh", response_model=RefreshOut)
async def refresh(_current: CurrentUserDep, session: SessionDep) -> RefreshOut:
    """Trigger the collect→summarise→publish pipeline now."""
    if not await codex_auth.is_authenticated():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Codex is not connected — authenticate in Settings first.",
        )
    try:
        b = await news_svc.refresh_briefing(session)
        return RefreshOut(ok=True, detail=f"briefing published ({len(b.bullets)} bullets)")
    except Exception as exc:
        return RefreshOut(ok=False, detail=f"refresh failed: {exc}")


# --- Codex device-code auth ---


class LoginStartOut(BaseModel):
    login_id: str
    verification_url: str
    user_code: str


class LoginStatusOut(BaseModel):
    status: str
    detail: str


class CodexStatusOut(BaseModel):
    authenticated: bool


@codex_router.post("/login", response_model=LoginStartOut)
async def codex_login_start(_current: CurrentUserDep) -> LoginStartOut:
    """Begin a device-code login; the owner opens the URL and enters the code."""
    try:
        state = await codex_auth.start_login()
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail=f"login start failed: {exc}"
        ) from exc
    return LoginStartOut(
        login_id=state.login_id,
        verification_url=state.verification_url,
        user_code=state.user_code,
    )


@codex_router.get("/login/{login_id}", response_model=LoginStatusOut)
async def codex_login_status(login_id: str, _current: CurrentUserDep) -> LoginStatusOut:
    state = codex_auth.login_status(login_id)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown login")
    return LoginStatusOut(status=state.status, detail=state.detail)


@codex_router.get("/status", response_model=CodexStatusOut)
async def codex_status(_current: CurrentUserDep) -> CodexStatusOut:
    return CodexStatusOut(authenticated=await codex_auth.is_authenticated())


class MessageOut(BaseModel):
    message: str


@codex_router.post("/logout", response_model=MessageOut)
async def codex_logout(_current: CurrentUserDep) -> MessageOut:
    await codex_auth.logout()
    return MessageOut(message="Codex disconnected")
