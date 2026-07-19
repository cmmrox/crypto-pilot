"""SMS one-time-password (OTP) service — the second factor for login and the
gate on guarded security-setting changes.

Design (SECURITY_GUIDELINES.md):
- Codes are cryptographically random, single-use, stored only as a keyed hash,
  expire in 5 minutes and die after 5 failed attempts.
- Delivery uses the notify.lk credentials directly and is *independent* of the
  `sms_enabled` alerts toggle — a login code must always be sendable.
- Resend is throttled (60 s cooldown) and total sends are capped per user per
  hour to prevent SMS-bombing / cost abuse.
- Codes never appear in logs, events or API responses. In test/e2e mode
  (`otp_test_mode`) the last code per phone is captured in-process so the suite
  can complete the flow; the capture is gated by the setting and never runs in
  production.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Literal

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.core.security import generate_otp, hash_otp, verify_otp_hash
from app.db.models import OtpChallenge, User
from app.notifier.gateway import NotifyLkGateway, SmsResult
from app.services.events import record_event
from app.services.notify_config import get_notify_config

OTP_TTL = dt.timedelta(minutes=5)
MAX_ATTEMPTS = 5
RESEND_COOLDOWN = dt.timedelta(seconds=60)
MAX_SENDS_PER_HOUR = 5

Purpose = Literal["login", "enable_2fa", "disable_2fa", "change_phone"]
PHONE_RE = re.compile(r"^94[0-9]{9}$")

# TEST/E2E ONLY — populated with the latest code by phone and by exact
# challenge. Challenge keys make concurrent browser logins deterministic.
_TEST_CODES: dict[str, str] = {}


class OtpError(Exception):
    """Base OTP failure."""


class OtpInvalid(OtpError):
    """The submitted code did not match."""


class OtpExpired(OtpError):
    """The challenge has expired or was already consumed."""


class OtpLocked(OtpError):
    """The challenge exhausted its attempt budget."""


class OtpThrottled(OtpError):
    """Resend cooldown or hourly send cap hit."""


class OtpSendError(OtpError):
    """The code could not be delivered (SMS not configured or provider failed)."""


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def normalize_phone(phone: str) -> str:
    """Return the notify.lk number form (9471XXXXXXX): digits only, no '+'."""
    normalized = phone.lstrip("+").replace(" ", "").replace("-", "")
    if PHONE_RE.fullmatch(normalized) is None:
        raise ValueError("phone must use notify.lk format 94XXXXXXXXX")
    return normalized


def phone_hint(phone: str) -> str:
    """Masked display form, e.g. '···· 1234'."""
    tail = phone[-4:] if len(phone) >= 4 else phone
    return f"···· {tail}"


async def _sends_last_hour(session: AsyncSession, user_id: int) -> int:
    since = _now() - dt.timedelta(hours=1)
    # Count individual sends across all of the user's recent challenges.
    stmt = (
        select(func.coalesce(func.sum(OtpChallenge.send_count), 0))
        .where(OtpChallenge.user_id == user_id)
        .where(OtpChallenge.created_at > since)
    )
    return int((await session.execute(stmt)).scalar_one())


async def _deliver(
    session: AsyncSession, phone: str, code: str, *, challenge_id: int
) -> SmsResult:
    """Send the code via notify.lk, independent of the alerts toggle."""
    settings = get_settings()
    if settings.otp_test_mode:
        _TEST_CODES[phone] = code
        _TEST_CODES[f"challenge:{challenge_id}"] = code
        return SmsResult(True, "captured (test mode)")

    cfg = await get_notify_config(session)
    if cfg is None:
        return SmsResult(False, "SMS is not configured")
    message = f"CryptoPilot verification code: {code} (valid 5 min). Do not share it."
    gateway = NotifyLkGateway(cfg.user_id, cfg.api_key, cfg.sender_id)
    try:
        return await gateway.send(phone, message)
    finally:
        await gateway.close()


async def start_challenge(
    session: AsyncSession, *, user: User, purpose: Purpose, phone: str
) -> OtpChallenge:
    """Create a challenge, send the code, and return the (unconsumed) row.

    Raises OtpThrottled if the hourly send cap is reached, OtpSendError if the
    code cannot be delivered.
    """
    normalized = normalize_phone(phone)
    # Serialize challenge creation per owner so simultaneous requests cannot
    # race past the hourly send cap.
    await session.execute(select(User.id).where(User.id == user.id).with_for_update())
    if (
        not get_settings().otp_test_disable_throttle
        and await _sends_last_hour(session, user.id) >= MAX_SENDS_PER_HOUR
    ):
        raise OtpThrottled("too many verification codes requested — try again later")

    code = generate_otp()
    now = _now()
    challenge = OtpChallenge(
        user_id=user.id,
        purpose=purpose,
        code_hash=hash_otp(code),
        phone_encrypted=encrypt(normalized, get_settings().master_key),
        attempts=0,
        max_attempts=MAX_ATTEMPTS,
        expires_at=now + OTP_TTL,
        last_sent_at=now,
        send_count=1,
    )
    session.add(challenge)
    await session.flush()
    # Persist the challenge before calling the external provider. This avoids
    # holding a database transaction open across network I/O and preserves a
    # durable record even when delivery fails.
    await session.commit()

    result = await _deliver(session, normalized, code, challenge_id=challenge.id)
    await record_event(
        session,
        level="INFO" if result.ok else "ERROR",
        category="security",
        message=f"OTP code {'sent' if result.ok else 'send failed'} ({purpose})",
        ref=f"otp_send:{purpose}:{user.email}",
        sms_status="delivered" if result.ok else "failed",
        payload={"purpose": purpose, "challenge_id": challenge.id},
    )
    await session.commit()
    if not result.ok:
        raise OtpSendError("verification code delivery failed")
    return challenge


async def resend(
    session: AsyncSession,
    challenge_id: int,
    *,
    user_id: int,
    expected_purpose: Purpose,
) -> OtpChallenge:
    """Re-send a fresh code for an existing challenge, honouring the cooldown.

    A new code is generated (the old hash is overwritten) so a resend fully
    supersedes the previous code.
    """
    # Lock the owner before the challenge. start_challenge uses the same owner
    # lock, making the hourly cap atomic across parallel challenges/resends.
    user = (
        await session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
    ).scalar_one_or_none()
    if user is None:
        raise OtpExpired("verification challenge not found")
    challenge = await _load_active(session, challenge_id)
    if challenge.user_id != user_id or challenge.purpose != expected_purpose:
        raise OtpExpired("verification challenge not found")
    if challenge.attempts >= challenge.max_attempts:
        raise OtpLocked("too many incorrect attempts")
    now = _now()
    if now - challenge.last_sent_at < RESEND_COOLDOWN:
        raise OtpThrottled("please wait before requesting another code")

    if (
        not get_settings().otp_test_disable_throttle
        and await _sends_last_hour(session, user.id) >= MAX_SENDS_PER_HOUR
    ):
        raise OtpThrottled("too many verification codes requested — try again later")

    phone = decrypt(challenge.phone_encrypted, get_settings().master_key)
    code = generate_otp()
    challenge.code_hash = hash_otp(code)
    challenge.last_sent_at = now
    challenge.send_count += 1
    # The new code gets a fresh validity window, but the verification-attempt
    # budget belongs to the challenge lifetime. A resend must never revive an
    # exhausted challenge or grant more online guesses.
    challenge.expires_at = now + OTP_TTL
    await session.flush()
    await session.commit()

    result = await _deliver(session, phone, code, challenge_id=challenge.id)
    await record_event(
        session,
        level="INFO" if result.ok else "ERROR",
        category="security",
        message=f"OTP code resent ({challenge.purpose})",
        ref=f"otp_resend:{challenge.purpose}:{user.email}",
        sms_status="delivered" if result.ok else "failed",
        payload={"purpose": challenge.purpose, "challenge_id": challenge.id},
    )
    await session.commit()
    if not result.ok:
        raise OtpSendError("verification code delivery failed")
    return challenge


async def verify(
    session: AsyncSession,
    challenge_id: int,
    code: str,
    *,
    commit_failure: bool = True,
) -> OtpChallenge:
    """Verify a code against a challenge, consuming it on success.

    Raises OtpExpired / OtpLocked / OtpInvalid. Every failure increments the
    attempt counter so a challenge dies after MAX_ATTEMPTS wrong guesses.
    """
    challenge = await _load_active(session, challenge_id)
    if challenge.attempts >= challenge.max_attempts:
        raise OtpLocked("too many incorrect attempts")

    if not verify_otp_hash(code, challenge.code_hash):
        challenge.attempts += 1
        await session.flush()
        # Failed verification is security state, not disposable request state.
        # Most callers commit here before raising. Login verification opts out
        # so its attempt increment and account-wide failure event can commit
        # atomically while the owner row remains locked.
        if commit_failure:
            await session.commit()
        if challenge.attempts >= challenge.max_attempts:
            raise OtpLocked("too many incorrect attempts")
        raise OtpInvalid("incorrect verification code")

    challenge.consumed_at = _now()
    await session.flush()
    return challenge


async def _load_active(session: AsyncSession, challenge_id: int) -> OtpChallenge:
    challenge = (
        await session.execute(
            select(OtpChallenge)
            .where(OtpChallenge.id == challenge_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if challenge is None:
        raise OtpExpired("verification challenge not found")
    if challenge.consumed_at is not None:
        raise OtpExpired("verification code already used")
    if challenge.expires_at <= _now():
        raise OtpExpired("verification code expired")
    return challenge


def challenge_phone(challenge: OtpChallenge) -> str:
    """Decrypt the target phone for a challenge (for display hints)."""
    return decrypt(challenge.phone_encrypted, get_settings().master_key)


def user_phone(user: User) -> str | None:
    """Decrypt the owner's enrolled 2FA number (normalized), or None."""
    if user.phone_encrypted is None:
        return None
    return decrypt(user.phone_encrypted, get_settings().master_key)


async def cleanup_expired(session: AsyncSession) -> int:
    """Delete challenges that can no longer be used.

    Called from the existing four-hour ingest tick; security events remain the
    permanent audit trail while short-lived code hashes are removed.
    """
    now = _now()
    result = await session.execute(
        delete(OtpChallenge).where(
            or_(
                OtpChallenge.expires_at <= now,
                OtpChallenge.consumed_at.is_not(None),
            )
        )
    )
    return int(result.rowcount or 0)


async def invalidate_user_challenges(
    session: AsyncSession, user_id: int, *, except_id: int | None = None
) -> int:
    """Consume every active challenge for a user.

    Credential/2FA recovery and phone changes must invalidate pending login and
    settings authorizations so an older code cannot mint a new session or undo
    a freshly secured state.
    """
    stmt = (
        update(OtpChallenge)
        .where(
            OtpChallenge.user_id == user_id,
            OtpChallenge.consumed_at.is_(None),
        )
        .values(consumed_at=_now())
    )
    if except_id is not None:
        stmt = stmt.where(OtpChallenge.id != except_id)
    result = await session.execute(stmt)
    return int(result.rowcount or 0)
