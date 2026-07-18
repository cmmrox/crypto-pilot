"""Notifier service: event → SMS via notify.lk, fire-and-log with 3 retries.

An SMS failure never blocks trading (BSD §10). Every attempt updates the event's
sms_status so the ledger shows delivery outcomes.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.notifier.gateway import SmsGateway
from app.notifier.templates import render
from app.services.events import record_event

_log = get_logger("notifier")

MAX_ATTEMPTS = 3
BACKOFF_BASE_S = 0.5


async def notify(
    session: AsyncSession,
    gateway: SmsGateway,
    *,
    kind: str,
    to: str,
    payload: dict[str, object],
    enabled: bool = True,
) -> str:
    """Render + send an SMS for an event, with retries. Returns the sms_status.

    Records a `sms` audit event with the final delivery status. Never raises —
    trading must not be blocked by SMS problems.
    """
    if not enabled:
        return "disabled"
    try:
        message = render(kind, payload)
    except KeyError:
        message = f"CryptoPilot event: {kind}"

    status = "failed"
    last_detail = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result = await gateway.send(to, message)
        if result.ok:
            status = "delivered" if attempt == 1 else "recovered"
            last_detail = result.detail
            break
        last_detail = result.detail
        _log.warning("sms_retry", kind=kind, attempt=attempt, detail=result.detail)
        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(BACKOFF_BASE_S * attempt)

    level = "INFO" if status in ("delivered", "recovered") else "ERROR"
    await record_event(
        session,
        level=level,  # type: ignore[arg-type]
        category="sms",
        message=f"SMS {status} for {kind}",
        ref=f"sms:{kind}",
        sms_status=status,
        payload={"kind": kind, "detail": last_detail},
    )
    return status
