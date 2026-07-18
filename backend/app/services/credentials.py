"""Encrypted API-credential storage (AES-GCM) and connection testing.

Secrets are write-only from the UI: stored encrypted, never returned. A masked
hint (last 4 chars of the key) is the only thing exposed back.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.db.models import ApiCredential


@dataclass(frozen=True)
class CredentialStatus:
    service: str
    environment: str
    configured: bool
    key_hint: str | None  # last 4 of the API key, or None


async def save_credential(
    session: AsyncSession,
    *,
    environment: str,
    service: str,
    api_key: str,
    api_secret: str,
) -> None:
    """Store or replace an encrypted credential pair for (environment, service)."""
    master = get_settings().master_key
    secret_enc = encrypt(api_secret, master)
    existing = (
        await session.execute(
            select(ApiCredential).where(
                ApiCredential.environment == environment, ApiCredential.service == service
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            ApiCredential(
                environment=environment,
                service=service,
                api_key=api_key,
                secret_encrypted=secret_enc,
            )
        )
    else:
        existing.api_key = api_key
        existing.secret_encrypted = secret_enc


async def get_decrypted(
    session: AsyncSession, *, environment: str, service: str
) -> tuple[str, str] | None:
    """Return (api_key, api_secret) decrypted, or None if not configured."""
    row = (
        await session.execute(
            select(ApiCredential).where(
                ApiCredential.environment == environment, ApiCredential.service == service
            )
        )
    ).scalar_one_or_none()
    if row is None or row.api_key is None:
        return None
    return row.api_key, decrypt(row.secret_encrypted, get_settings().master_key)


async def get_status(
    session: AsyncSession, *, environment: str, service: str
) -> CredentialStatus:
    """Return whether a credential is configured plus a masked key hint."""
    row = (
        await session.execute(
            select(ApiCredential).where(
                ApiCredential.environment == environment, ApiCredential.service == service
            )
        )
    ).scalar_one_or_none()
    if row is None or row.api_key is None:
        return CredentialStatus(service, environment, configured=False, key_hint=None)
    hint = f"····{row.api_key[-4:]}" if len(row.api_key) >= 4 else "····"
    return CredentialStatus(service, environment, configured=True, key_hint=hint)
