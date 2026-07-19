"""Settings API: API-credential entry (write-only) and connection testing."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.api.schemas import (
    ConnectionTestOut,
    CredentialIn,
    CredentialStatusOut,
    MessageResponse,
    SecurityChangeConfirm,
    SecurityChangeStart,
    SecurityChangeStartOut,
    SecurityStatusOut,
)
from app.bot.service import bot_service
from app.bot.state import BotStatus
from app.db.session import get_session
from app.execution.binance_client import BinanceClient, BinanceError
from app.services import auth as auth_service
from app.services import credentials as cred_svc
from app.services import notify_config as notify_svc
from app.services.events import record_event
from app.services.settings_store import get_settings_row

router = APIRouter(prefix="/api/settings", tags=["settings"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/credentials/{environment}/{service}", response_model=CredentialStatusOut)
async def credential_status(
    environment: Literal["DEMO", "LIVE"],
    service: Literal["binance"],
    _current: CurrentUserDep,
    session: SessionDep,
) -> CredentialStatusOut:
    """Return whether a credential is configured (masked hint only, never the secret)."""
    status = await cred_svc.get_status(session, environment=environment, service=service)
    return CredentialStatusOut(
        service=status.service,
        environment=status.environment,
        configured=status.configured,
        key_hint=status.key_hint,
    )


@router.put("/credentials", response_model=MessageResponse)
async def save_credential(
    body: CredentialIn, current: CurrentUserDep, session: SessionDep
) -> MessageResponse:
    """Store or replace an encrypted credential pair (write-only)."""
    try:
        await auth_service.require_password_reauth(
            session,
            current.user,
            body.current_password,
            action=f"replace_{body.environment}_binance_credentials",
        )
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except auth_service.RateLimitedError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    # This is the same lock used by bot start and operational setting changes.
    await get_settings_row(session, for_update=True)
    if (await bot_service.status(session)).status != BotStatus.STOPPED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="stop the bot before replacing exchange credentials",
        )
    await cred_svc.save_credential(
        session,
        environment=body.environment,
        service=body.service,
        api_key=body.api_key,
        api_secret=body.api_secret,
    )
    await record_event(
        session,
        level="INFO",
        category="security",
        message=f"{body.service} credentials updated for {body.environment}",
        ref=f"cred_update:{body.environment}:{body.service}",
        payload={"environment": body.environment, "service": body.service},
    )
    await session.commit()
    return MessageResponse(message="credentials stored")


@router.post("/credentials/{environment}/binance/test", response_model=ConnectionTestOut)
async def test_binance_connection(
    environment: str, _current: CurrentUserDep, session: SessionDep
) -> ConnectionTestOut:
    """Test the Binance connection for an environment.

    Public reachability is always checked. If a key pair is configured, a signed
    account call verifies the credentials too.
    """
    creds = await cred_svc.get_decrypted(session, environment=environment, service="binance")
    try:
        async with BinanceClient(
            environment,
            api_key=creds[0] if creds else None,
            api_secret=creds[1] if creds else None,
        ) as client:
            drift = await client.clock_drift_ms()
            if creds is None:
                return ConnectionTestOut(
                    ok=True,
                    detail=f"Public market data reachable (clock drift {drift} ms). "
                    "No API key configured — add one to verify account access.",
                )
            await client.signed_request("GET", "/fapi/v2/balance")
            return ConnectionTestOut(
                ok=True,
                detail=f"Authenticated account access verified (clock drift {drift} ms).",
            )
    except BinanceError as exc:
        return ConnectionTestOut(ok=False, detail=f"Connection failed: {exc}")


# --- notify.lk SMS ---


class SmsConfigIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    api_key: str = Field(min_length=1, max_length=256)
    sender_id: str = Field(min_length=1, max_length=32)
    phone: str = Field(min_length=9, max_length=15)
    current_password: str = Field(min_length=1, max_length=256)


class SmsStatusOut(BaseModel):
    configured: bool
    sender_id: str | None
    phone_hint: str | None
    sms_enabled: bool


class SmsToggleIn(BaseModel):
    enabled: bool


@router.get("/sms", response_model=SmsStatusOut)
async def sms_status(_current: CurrentUserDep, session: SessionDep) -> SmsStatusOut:
    st = await notify_svc.config_status(session)
    return SmsStatusOut(
        configured=bool(st["configured"]),
        sender_id=st["sender_id"],
        phone_hint=st["phone_hint"],
        sms_enabled=bool(st["sms_enabled"]),
    )


@router.put("/sms", response_model=MessageResponse)
async def save_sms(
    body: SmsConfigIn, current: CurrentUserDep, session: SessionDep
) -> MessageResponse:
    try:
        await auth_service.require_password_reauth(
            session,
            current.user,
            body.current_password,
            action="replace_notify_credentials",
        )
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except auth_service.RateLimitedError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    await notify_svc.save_notify_config(
        session,
        user_id=body.user_id,
        api_key=body.api_key,
        sender_id=body.sender_id,
        phone=body.phone,
    )
    await record_event(
        session,
        level="INFO",
        category="security",
        message="notify.lk SMS credentials updated",
        ref="sms_config",
        payload={"sender_id": body.sender_id},
    )
    await session.commit()
    return MessageResponse(message="SMS credentials stored")


@router.post("/sms/toggle", response_model=MessageResponse)
async def toggle_sms(
    body: SmsToggleIn, current: CurrentUserDep, session: SessionDep
) -> MessageResponse:
    row = await get_settings_row(session)
    row.sms_enabled = body.enabled
    await record_event(
        session,
        level="INFO",
        category="security",
        message=f"SMS alerts {'enabled' if body.enabled else 'disabled'}",
        ref="sms_alerts_toggle",
        payload={"enabled": body.enabled},
    )
    # Security-affecting state must be durable before the 200 response so an
    # immediate read cannot observe the previous value.
    await session.commit()
    return MessageResponse(message=f"SMS {'enabled' if body.enabled else 'disabled'}")


@router.post("/sms/test", response_model=ConnectionTestOut)
async def test_sms(_current: CurrentUserDep, session: SessionDep) -> ConnectionTestOut:
    """Send a real test SMS to the configured phone."""
    cfg = await notify_svc.get_notify_config(session)
    if cfg is None:
        return ConnectionTestOut(ok=False, detail="No SMS credentials configured.")
    from app.notifier.gateway import NotifyLkGateway

    gw = NotifyLkGateway(cfg.user_id, cfg.api_key, cfg.sender_id)
    try:
        result = await gw.send(cfg.phone, "CryptoPilot: test SMS — notifications are working.")
    finally:
        await gw.close()
    return ConnectionTestOut(ok=result.ok, detail=result.detail)


# --- Two-factor authentication (SMS) ---


@router.get("/security", response_model=SecurityStatusOut)
async def security_status(current: CurrentUserDep, _session: SessionDep) -> SecurityStatusOut:
    """Return the owner's 2FA state (masked phone hint only)."""
    st = auth_service.security_status(current.user)
    return SecurityStatusOut(twofa_enabled=bool(st["twofa_enabled"]), phone_hint=st["phone_hint"])


@router.post("/security/2fa/start", response_model=SecurityChangeStartOut)
async def security_change_start(
    body: SecurityChangeStart, current: CurrentUserDep, session: SessionDep
) -> SecurityChangeStartOut:
    """Re-auth with the password and send an OTP to complete a 2FA change."""
    try:
        challenge = await auth_service.start_security_change(
            session,
            current.user,
            action=body.action,
            password=body.password,
            new_phone=body.new_phone,
        )
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except auth_service.RateLimitedError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except auth_service.TwoFactorError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    hint = None
    if body.new_phone:
        from app.services.otp import normalize_phone, phone_hint

        hint = phone_hint(normalize_phone(body.new_phone))
    return SecurityChangeStartOut(challenge_id=challenge.id, phone_hint=hint)


@router.post("/security/2fa/confirm", response_model=MessageResponse)
async def security_change_confirm(
    body: SecurityChangeConfirm, current: CurrentUserDep, session: SessionDep
) -> MessageResponse:
    """Verify the OTP and commit the pending 2FA change."""
    try:
        message = await auth_service.confirm_security_change(
            session,
            current.user,
            body.challenge_id,
            body.code,
            current_sid=current.sid,
        )
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except auth_service.TwoFactorError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageResponse(message=message)
