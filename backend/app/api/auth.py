"""Authentication routes: login → TOTP → tokens, refresh, logout, sessions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.api.schemas import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    MessageResponse,
    RefreshRequest,
    TokenResponse,
    TotpRequest,
)
from app.core.security import TokenError, decode_token
from app.db.session import get_session
from app.services import auth as auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    session: SessionDep,
    user_agent: Annotated[str | None, Header()] = None,
) -> LoginResponse:
    """Verify password; returns a short-lived token to complete TOTP."""
    try:
        totp_token = await auth_service.authenticate_password(
            session, body.email, body.password, user_agent=user_agent
        )
    except auth_service.RateLimitedError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return LoginResponse(totp_token=totp_token)


@router.post("/totp", response_model=TokenResponse)
async def verify_totp(
    body: TotpRequest,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
    user_agent: Annotated[str | None, Header()] = None,
) -> TokenResponse:
    """Complete login by verifying the authenticator code."""
    token = _bearer_value(authorization)
    try:
        claims = decode_token(token, expected_purpose="totp_pending")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    try:
        access, refresh = await auth_service.verify_totp_and_issue(
            session, int(claims["sub"]), body.code, user_agent=user_agent
        )
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, session: SessionDep) -> TokenResponse:
    """Issue a fresh access token from a valid refresh token."""
    try:
        claims = decode_token(body.refresh_token, expected_purpose="refresh")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    try:
        access = await auth_service.refresh_access(
            session, claims["sid"], claims["jti"], int(claims["sub"])
        )
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    # Return the same refresh token (rotation happens on re-login); access is renewed.
    return TokenResponse(access_token=access, refresh_token=body.refresh_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(current: CurrentUserDep, session: SessionDep) -> MessageResponse:
    """Revoke the current session."""
    await auth_service.revoke_session(session, current.sid)
    return MessageResponse(message="signed out")


@router.post("/sessions/revoke-others", response_model=MessageResponse)
async def revoke_others(current: CurrentUserDep, session: SessionDep) -> MessageResponse:
    """Revoke every other session for this owner."""
    count = await auth_service.revoke_other_sessions(session, current.user.id, current.sid)
    return MessageResponse(message=f"revoked {count} other session(s)")


@router.get("/me", response_model=MeResponse)
async def me(current: CurrentUserDep) -> MeResponse:
    """Return the current owner's identity."""
    return MeResponse(email=current.user.email, role=current.user.role)


def _bearer_value(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    return authorization.split(" ", 1)[1]
