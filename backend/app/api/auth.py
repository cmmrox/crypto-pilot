"""Authentication routes: login → SMS OTP → tokens, refresh, logout, sessions."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.api.schemas import (
    DevOtpOut,
    LoginRequest,
    LoginResponse,
    MeResponse,
    MessageResponse,
    OtpVerifyRequest,
    RefreshRequest,
    TokenResponse,
)
from app.core.config import get_settings
from app.core.security import TokenError, decode_token
from app.db.models import User
from app.db.session import get_session
from app.services import auth as auth_service
from app.services import otp as otp_service
from app.services.events import record_event

router = APIRouter(prefix="/api/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    session: SessionDep,
    user_agent: Annotated[str | None, Header()] = None,
) -> LoginResponse:
    """Verify the password.

    With 2FA off, returns tokens directly. With 2FA on, sends an SMS code and
    returns a short-lived otp_token to complete via /api/auth/otp/verify.
    """
    try:
        result = await auth_service.authenticate_password(
            session, body.email, body.password, user_agent=user_agent
        )
    except auth_service.RateLimitedError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return LoginResponse(
        mode=result.mode,
        access_token=result.access,
        refresh_token=result.refresh,
        otp_token=result.otp_token,
        phone_hint=result.phone_hint,
    )


@router.post("/otp/verify", response_model=TokenResponse)
async def verify_otp(
    body: OtpVerifyRequest,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
    user_agent: Annotated[str | None, Header()] = None,
) -> TokenResponse:
    """Complete login by verifying the SMS code bound to the otp_token."""
    claims = _otp_pending_claims(authorization)
    try:
        access, refresh = await auth_service.verify_otp_and_issue(
            session,
            int(claims["sub"]),
            int(claims["cid"]),
            body.code,
            user_agent=user_agent,
        )
    except auth_service.RateLimitedError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/otp/resend", response_model=MessageResponse)
async def resend_otp(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> MessageResponse:
    """Re-send the login SMS code for the challenge bound to the otp_token."""
    claims = _otp_pending_claims(authorization)
    try:
        await auth_service.resend_login_otp(
            session,
            user_id=int(claims["sub"]),
            challenge_id=int(claims["cid"]),
        )
    except (auth_service.RateLimitedError, otp_service.OtpThrottled) as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except (auth_service.AuthError, otp_service.OtpExpired, otp_service.OtpLocked) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except otp_service.OtpSendError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="could not send verification code"
        ) from exc
    return MessageResponse(message="a new code was sent")


@router.get("/otp/dev-code", response_model=DevOtpOut)
async def dev_code(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
    challenge_id: Annotated[int | None, Query(gt=0)] = None,
    email: Annotated[str | None, Query()] = None,
    phone: Annotated[str | None, Query()] = None,
) -> DevOtpOut:
    """TEST/E2E ONLY: return the code for an exact challenge when available.

    404s unless CP_OTP_TEST_MODE is enabled. Never available in production.
    """
    settings = get_settings()
    if settings.environment != "test" or not settings.otp_test_mode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not found")
    if authorization is not None:
        claims = _otp_pending_claims(authorization)
        challenge_id = int(claims["cid"])
    if challenge_id is not None:
        code = otp_service._TEST_CODES.get(f"challenge:{challenge_id}")
        if code is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no code available")
        return DevOtpOut(code=code)

    target = otp_service.normalize_phone(phone) if phone else None
    if target is None and email is not None:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        target = otp_service.user_phone(user) if user else None
    code = otp_service._TEST_CODES.get(target) if target else None
    if code is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no code available")
    return DevOtpOut(code=code)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, session: SessionDep) -> TokenResponse:
    """Issue a fresh access token from a valid refresh token."""
    try:
        claims = decode_token(body.refresh_token, expected_purpose="refresh")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    try:
        access, rotated_refresh = await auth_service.refresh_access(
            session, claims["sid"], claims["jti"], int(claims["sub"])
        )
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return TokenResponse(access_token=access, refresh_token=rotated_refresh)


@router.post("/logout", response_model=MessageResponse)
async def logout(current: CurrentUserDep, session: SessionDep) -> MessageResponse:
    """Revoke the current session."""
    await auth_service.revoke_session(session, current.sid)
    return MessageResponse(message="signed out")


@router.post("/sessions/revoke-others", response_model=MessageResponse)
async def revoke_others(current: CurrentUserDep, session: SessionDep) -> MessageResponse:
    """Revoke every other session for this owner."""
    count = await auth_service.revoke_other_sessions(session, current.user.id, current.sid)
    await record_event(
        session,
        level="INFO",
        category="security",
        message="Other sessions revoked",
        ref=f"sessions_revoked:{current.user.email}",
        payload={"email": current.user.email, "revoked": count},
    )
    await session.commit()
    return MessageResponse(message=f"revoked {count} other session(s)")


@router.get("/me", response_model=MeResponse)
async def me(current: CurrentUserDep) -> MeResponse:
    """Return the current owner's identity."""
    return MeResponse(email=current.user.email, role=current.user.role)


def _bearer_value(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    return authorization.split(" ", 1)[1]


def _otp_pending_claims(authorization: str | None) -> dict[str, Any]:
    """Decode an otp_pending bearer token, requiring the challenge-id claim."""
    token = _bearer_value(authorization)
    try:
        claims = decode_token(token, expected_purpose="otp_pending")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    if "cid" not in claims:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    return claims
