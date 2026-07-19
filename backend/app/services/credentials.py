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
    key_enc = encrypt(api_key, master)
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
                api_key=None,
                api_key_encrypted=key_enc,
                secret_encrypted=secret_enc,
            )
        )
    else:
        existing.api_key = None
        existing.api_key_encrypted = key_enc
        existing.secret_encrypted = secret_enc


async def migrate_plaintext_keys(session: AsyncSession) -> int:
    """Encrypt and clear every legacy plaintext API-key slot.

    The schema migration cannot receive ``CP_MASTER_KEY``, so the application
    performs this data migration before it starts serving traffic. Rows that
    already have an encrypted value still have any stale plaintext copy
    removed. The same storage slot contains the notify.lk user id.
    """
    rows = (
        await session.execute(
            select(ApiCredential)
            .where(ApiCredential.api_key.is_not(None))
            .with_for_update()
        )
    ).scalars()
    master = get_settings().master_key
    migrated = 0
    for row in rows:
        plaintext = row.api_key
        if plaintext is None:
            continue
        if row.api_key_encrypted is None:
            row.api_key_encrypted = encrypt(plaintext, master)
        row.api_key = None
        migrated += 1
    return migrated


def _decrypted_key(row: ApiCredential) -> str | None:
    """Read an encrypted key and lazily migrate pre-upgrade plaintext rows."""
    master = get_settings().master_key
    if row.api_key_encrypted is not None:
        return decrypt(row.api_key_encrypted, master)
    if row.api_key is None:
        return None
    plaintext = row.api_key
    row.api_key_encrypted = encrypt(plaintext, master)
    row.api_key = None
    return plaintext


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
    if row is None:
        return None
    api_key = _decrypted_key(row)
    if api_key is None:
        return None
    return api_key, decrypt(row.secret_encrypted, get_settings().master_key)


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
    if row is None:
        return CredentialStatus(service, environment, configured=False, key_hint=None)
    api_key = _decrypted_key(row)
    if api_key is None:
        return CredentialStatus(service, environment, configured=False, key_hint=None)
    hint = f"····{api_key[-4:]}" if len(api_key) >= 4 else "····"
    return CredentialStatus(service, environment, configured=True, key_hint=hint)
