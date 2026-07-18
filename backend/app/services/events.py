"""Event recording — the owner-facing audit trail (LOGGING_GUIDELINES.md).

Every operationally-significant action writes an events row with a reconstructable
payload. This is the spine of auditability (BSD G5).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Event

Level = Literal["INFO", "WARN", "ERROR"]
Category = Literal[
    "trade",
    "bot",
    "breaker",
    "error",
    "sms",
    "news",
    "reconciliation",
    "system",
    "security",
    "strategy",
]

_log = get_logger("events")


async def record_event(
    session: AsyncSession,
    *,
    level: Level,
    category: Category,
    message: str,
    payload: dict[str, Any] | None = None,
    ref: str | None = None,
    sms_status: str | None = None,
) -> Event:
    """Persist an audit event and mirror it to structured logs.

    The caller controls the transaction; this only adds+flushes so the row id is
    available. Secrets must never be placed in `payload` (log scrubber is a backstop).
    """
    event = Event(
        ts=dt.datetime.now(dt.UTC),
        level=level,
        category=category,
        message=message,
        payload_json=payload or {},
        ref=ref,
        sms_status=sms_status,
    )
    session.add(event)
    await session.flush()
    _log.info(
        "event_recorded",
        event_id=event.id,
        level=level,
        category=category,
        message=message,
        ref=ref,
    )
    return event


async def record_event_committed(
    *,
    level: Level,
    category: Category,
    message: str,
    payload: dict[str, Any] | None = None,
    ref: str | None = None,
    sms_status: str | None = None,
) -> None:
    """Record an event in its own committed transaction.

    Use for audit events that must survive even when the surrounding request is
    rolled back — e.g. failed logins and lockouts, which happen on the error path
    but must durably accumulate for rate limiting (BSD G5 auditability).
    """
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        await record_event(
            session,
            level=level,
            category=category,
            message=message,
            payload=payload,
            ref=ref,
            sms_status=sms_status,
        )
        await session.commit()
