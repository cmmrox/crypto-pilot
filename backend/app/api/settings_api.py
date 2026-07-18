"""Settings API: API-credential entry (write-only) and connection testing."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.api.schemas import (
    ConnectionTestOut,
    CredentialIn,
    CredentialStatusOut,
    MessageResponse,
)
from app.db.session import get_session
from app.execution.binance_client import BinanceClient, BinanceError
from app.services import credentials as cred_svc
from app.services.events import record_event

router = APIRouter(prefix="/api/settings", tags=["settings"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/credentials/{environment}/{service}", response_model=CredentialStatusOut)
async def credential_status(
    environment: str, service: str, _current: CurrentUserDep, session: SessionDep
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
    return MessageResponse(message="credentials stored")


@router.post(
    "/credentials/{environment}/binance/test", response_model=ConnectionTestOut
)
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
