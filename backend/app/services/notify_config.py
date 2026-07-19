"""notify.lk configuration storage (encrypted) + a high-level event→SMS helper.

Config (user_id, api_key, sender_id, phone) is stored as an encrypted JSON blob in
api_credentials(service='notifylk'). The bot calls notify_event(...) at key moments;
it no-ops silently when SMS is disabled or unconfigured — trading is never blocked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.core.logging import get_logger
from app.db.models import ApiCredential
from app.notifier.gateway import NotifyLkGateway
from app.notifier.service import notify
from app.services.settings_store import get_settings_row

_log = get_logger("notify_config")
_SERVICE = "notifylk"


@dataclass(frozen=True)
class NotifyConfig:
    user_id: str
    api_key: str
    sender_id: str
    phone: str


async def save_notify_config(
    session: AsyncSession, *, user_id: str, api_key: str, sender_id: str, phone: str
) -> None:
    """Store or replace the encrypted notify.lk config."""
    master = get_settings().master_key
    blob = encrypt(
        json.dumps({"api_key": api_key, "sender_id": sender_id, "phone": phone}),
        master,
    )
    user_id_encrypted = encrypt(user_id, master)
    row = (
        await session.execute(select(ApiCredential).where(ApiCredential.service == _SERVICE))
    ).scalar_one_or_none()
    if row is None:
        session.add(
            ApiCredential(
                environment="ALL",
                service=_SERVICE,
                api_key=None,
                api_key_encrypted=user_id_encrypted,
                secret_encrypted=blob,
            )
        )
    else:
        row.api_key = None
        row.api_key_encrypted = user_id_encrypted
        row.secret_encrypted = blob


async def get_notify_config(session: AsyncSession) -> NotifyConfig | None:
    row = (
        await session.execute(select(ApiCredential).where(ApiCredential.service == _SERVICE))
    ).scalar_one_or_none()
    if row is None:
        return None
    master = get_settings().master_key
    if row.api_key_encrypted is not None:
        user_id = decrypt(row.api_key_encrypted, master)
    elif row.api_key is not None:
        # Compatibility for pre-encryption rows. Migrate on first access so an
        # existing notify.lk installation keeps working across the upgrade.
        user_id = row.api_key
        row.api_key_encrypted = encrypt(user_id, master)
        row.api_key = None
    else:
        return None
    data = json.loads(decrypt(row.secret_encrypted, master))
    return NotifyConfig(
        user_id=user_id,
        api_key=data["api_key"],
        sender_id=data["sender_id"],
        phone=data["phone"],
    )


async def config_status(session: AsyncSession) -> dict[str, object]:
    cfg = await get_notify_config(session)
    settings_row = await get_settings_row(session)
    return {
        "configured": cfg is not None,
        "sender_id": cfg.sender_id if cfg else None,
        "phone_hint": ("···· " + cfg.phone[-4:]) if cfg else None,
        "sms_enabled": settings_row.sms_enabled,
    }


async def notify_event(session: AsyncSession, *, kind: str, payload: dict[str, object]) -> str:
    """Resolve config from the DB and send an event SMS. No-op if unconfigured/disabled."""
    settings_row = await get_settings_row(session)
    cfg = await get_notify_config(session)
    if cfg is None or not settings_row.sms_enabled:
        return "skipped"
    gateway = NotifyLkGateway(cfg.user_id, cfg.api_key, cfg.sender_id)
    try:
        return await notify(session, gateway, kind=kind, to=cfg.phone, payload=payload)
    finally:
        await gateway.close()
