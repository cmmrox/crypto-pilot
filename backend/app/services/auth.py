"""Authentication service: login, SMS OTP, sessions, rate limiting.

Rate limiting is DB-backed (recent failed-login security events) so it survives
restarts and is auditable. Sessions are server-side for real revocation.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import decrypt
from app.core.security import (
    create_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.db.models import Event, OtpChallenge, Session, User
from app.notifier.gateway import SmsResult
from app.services import otp as otp_service
from app.services.events import record_event, record_event_committed
from app.services.notify_config import NotifyConfig, get_notify_config

# Lockout policy
MAX_FAILURES = 5
LOCKOUT_WINDOW = dt.timedelta(minutes=15)
OTP_PENDING_TTL = dt.timedelta(minutes=5)

SecurityAction = Literal["enable", "disable", "change_phone"]

# A fixed Argon2id hash makes the nonexistent-user path perform the same
# expensive password verification as an existing-user path. It is not a
# credential and never grants access.
_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$X0mNLOVPpUIfeV320/KZBQ"
    "$6g0eAWlv2APt4uTRMtyqzTex9UhDD/A0MXrZYMHBvEo"
)


class AuthError(Exception):
    """Base authentication failure (maps to 401)."""


class RateLimitedError(Exception):
    """Too many recent failures (maps to 429)."""


class TwoFactorError(Exception):
    """A guarded 2FA settings change was rejected (maps to 400)."""


@dataclass(frozen=True)
class LoginResult:
    """Outcome of the password step: either full tokens (2FA off) or a pending
    OTP challenge (2FA on)."""

    mode: Literal["tokens", "otp"]
    access: str | None = None
    refresh: str | None = None
    otp_token: str | None = None
    phone_hint: str | None = None


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


async def _recent_failure_count(session: AsyncSession, email: str) -> int:
    """Count failed logins for this email since the later of the lockout window
    start and the most recent successful login.

    Resetting the counter on success is standard, correct behaviour: a legitimate
    owner who eventually signs in should not stay locked by earlier typos.
    """
    window_start = _now() - LOCKOUT_WINDOW
    last_success = (
        await session.execute(
            select(func.max(Event.ts)).where(
                Event.category == "security",
                Event.ref == f"login_ok:{email}",
            )
        )
    ).scalar_one_or_none()
    since = max(window_start, last_success) if last_success else window_start
    stmt = (
        select(func.count())
        .select_from(Event)
        .where(
            Event.category == "security",
            Event.ref == f"login_fail:{email}",
            Event.ts > since,
        )
    )
    return int((await session.execute(stmt)).scalar_one())


async def _recent_security_reauth_failures(
    session: AsyncSession, email: str, *, ref_prefix: str = "twofa_reauth_fail"
) -> int:
    """Count recent password failures on authenticated security changes."""
    stmt = (
        select(func.count())
        .select_from(Event)
        .where(
            Event.category == "security",
            Event.ref == f"{ref_prefix}:{email}",
            Event.ts > _now() - LOCKOUT_WINDOW,
        )
    )
    return int((await session.execute(stmt)).scalar_one())


async def require_password_reauth(
    session: AsyncSession,
    user: User,
    password: str,
    *,
    action: str,
    ref_prefix: str = "sensitive_reauth_fail",
) -> User:
    """Serialize and verify a fresh owner password for a sensitive action."""
    locked_user = (
        await session.execute(select(User).where(User.id == user.id).with_for_update())
    ).scalar_one_or_none()
    if locked_user is None:
        raise AuthError("account is no longer available")
    failures = await _recent_security_reauth_failures(
        session, locked_user.email, ref_prefix=ref_prefix
    )
    if failures >= MAX_FAILURES:
        raise RateLimitedError("security verification temporarily locked")
    if verify_password(password, locked_user.password_hash):
        return locked_user
    await record_event(
        session,
        level="WARN",
        category="security",
        message="Failed password verification for sensitive settings change",
        ref=f"{ref_prefix}:{locked_user.email}",
        payload={"email": locked_user.email, "action": action},
    )
    await session.commit()
    raise AuthError("incorrect password")


async def authenticate_password(
    session: AsyncSession, email: str, password: str, *, user_agent: str | None = None
) -> LoginResult:
    """Verify email+password.

    When 2FA is disabled, issues tokens directly (mode="tokens"). When enabled,
    sends an SMS code and returns a short-lived otp-pending token (mode="otp")
    bound to that challenge.

    Raises RateLimitedError when locked out, AuthError on bad credentials,
    RateLimitedError when the OTP send cap is hit, and AuthError if the code
    cannot be delivered.
    """
    # Serialize password checks for an existing account. The lock covers the
    # failure-count check and durable failure record, preventing parallel
    # requests from all observing the same pre-failure count.
    user = (
        await session.execute(select(User).where(User.email == email).with_for_update())
    ).scalar_one_or_none()
    failures = await _recent_failure_count(session, email)
    if failures >= MAX_FAILURES:
        await record_event(
            session,
            level="WARN",
            category="security",
            message="Login blocked — too many recent failures",
            ref=f"login_locked:{email}",
            payload={"email": email, "failures": failures},
        )
        await session.commit()
        raise RateLimitedError("account temporarily locked")

    candidate_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_ok = verify_password(password, candidate_hash)
    ok = user is not None and password_ok
    if not ok or user is None:
        await record_event(
            session,
            level="WARN",
            category="security",
            message="Failed login attempt",
            ref=f"login_fail:{email}",
            payload={"email": email, "user_agent": user_agent},
        )
        await session.commit()
        raise AuthError("invalid email or password")

    # Opportunistic password rehash if params strengthened
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    # 2FA disabled → single factor: issue a session immediately.
    if not user.twofa_enabled:
        access, refresh = await _issue_session(session, user, user_agent=user_agent)
        return LoginResult(mode="tokens", access=access, refresh=refresh)
    if user.phone_encrypted is None:
        await record_event_committed(
            level="ERROR",
            category="security",
            message="Login blocked — enabled 2FA has no enrolled phone",
            ref=f"twofa_invalid_state:{email}",
            payload={"email": email},
        )
        raise AuthError("two-factor configuration requires recovery")

    # 2FA enabled → send an SMS code and hand back an otp-pending token.
    phone = decrypt(user.phone_encrypted, get_settings().master_key)
    try:
        challenge = await otp_service.start_challenge(
            session, user=user, purpose="login", phone=phone
        )
    except otp_service.OtpThrottled as exc:
        raise RateLimitedError(str(exc)) from exc
    except otp_service.OtpSendError as exc:
        raise AuthError("could not send verification code — please try again") from exc

    await record_event(
        session,
        level="INFO",
        category="security",
        message="Password verified — awaiting SMS code",
        ref=f"login_pw_ok:{email}",
        payload={"email": email},
    )
    token = create_token(str(user.id), "otp_pending", OTP_PENDING_TTL, extra={"cid": challenge.id})
    return LoginResult(mode="otp", otp_token=token, phone_hint=otp_service.phone_hint(phone))


async def verify_otp_and_issue(
    session: AsyncSession,
    user_id: int,
    challenge_id: int,
    code: str,
    *,
    user_agent: str | None = None,
) -> tuple[str, str]:
    """Verify a login SMS code and issue access + refresh tokens.

    The challenge must belong to this user and be a login challenge — this is
    what stops an otp-pending token from being replayed against a different
    challenge. Wrong/locked codes are recorded as login failures (feeding the
    lockout) before raising.
    """
    # Serialize the aggregate lockout check with failure recording so parallel
    # OTP guesses cannot race past the account-wide five-attempt ceiling.
    user = (
        await session.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one_or_none()
    if user is None or not user.twofa_enabled:
        raise AuthError("two-factor not configured")
    failures = await _recent_failure_count(session, user.email)
    if failures >= MAX_FAILURES:
        await record_event(
            session,
            level="WARN",
            category="security",
            message="SMS verification blocked — account temporarily locked",
            ref=f"login_locked:{user.email}",
            payload={"email": user.email, "failures": failures},
        )
        await session.commit()
        raise RateLimitedError("account temporarily locked")

    challenge = (
        await session.execute(select(OtpChallenge).where(OtpChallenge.id == challenge_id))
    ).scalar_one_or_none()
    if challenge is None or challenge.user_id != user_id or challenge.purpose != "login":
        raise AuthError("invalid verification challenge")

    try:
        await otp_service.verify(session, challenge_id, code, commit_failure=False)
    except (otp_service.OtpInvalid, otp_service.OtpLocked) as exc:
        await record_event(
            session,
            level="WARN",
            category="security",
            message="Failed SMS code verification",
            ref=f"login_fail:{user.email}",
            payload={"email": user.email},
        )
        # Commit the per-challenge attempt and account-wide failure together
        # before releasing the owner lock.
        await session.commit()
        raise AuthError(str(exc)) from exc
    except otp_service.OtpExpired as exc:
        raise AuthError(str(exc)) from exc

    return await _issue_session(session, user, user_agent=user_agent)


async def _issue_session(
    session: AsyncSession, user: User, *, user_agent: str | None
) -> tuple[str, str]:
    settings = get_settings()
    sid = uuid.uuid4().hex
    refresh_jti = uuid.uuid4().hex
    expires = _now() + dt.timedelta(days=settings.jwt_refresh_ttl_days)
    session.add(
        Session(
            sid=sid,
            user_id=user.id,
            refresh_jti=refresh_jti,
            expires_at=expires,
            last_used_at=_now(),
            user_agent=user_agent,
        )
    )
    await record_event(
        session,
        level="INFO",
        category="security",
        message="Login successful",
        ref=f"login_ok:{user.email}",
        payload={"email": user.email, "sid": sid},
    )
    access = create_token(
        str(user.id),
        "access",
        dt.timedelta(minutes=settings.jwt_access_ttl_minutes),
        session_id=sid,
    )
    refresh = create_token(
        str(user.id),
        "refresh",
        dt.timedelta(days=settings.jwt_refresh_ttl_days),
        session_id=sid,
        extra={"jti": refresh_jti},
    )
    return access, refresh


async def refresh_access(
    session: AsyncSession, sid: str, refresh_jti: str, user_id: int
) -> tuple[str, str]:
    """Atomically rotate a valid refresh token and issue a fresh token pair."""
    row = (
        await session.execute(select(Session).where(Session.sid == sid).with_for_update())
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None or row.expires_at <= _now():
        raise AuthError("session is no longer valid")
    if row.refresh_jti != refresh_jti or row.user_id != user_id:
        # A validly-signed but stale refresh token indicates token-family
        # replay. Fail closed by revoking the complete server-side session so
        # no descendant refresh or access token remains usable.
        row.revoked_at = _now()
        row.refresh_jti = None
        await record_event(
            session,
            level="WARN",
            category="security",
            message="Refresh-token replay detected — session revoked",
            ref=f"refresh_replay:{sid}",
            payload={"sid": sid},
        )
        await session.commit()
        raise AuthError("session is no longer valid")
    settings = get_settings()
    next_refresh_jti = uuid.uuid4().hex
    row.refresh_jti = next_refresh_jti
    row.last_used_at = _now()
    access = create_token(
        str(user_id),
        "access",
        dt.timedelta(minutes=settings.jwt_access_ttl_minutes),
        session_id=sid,
    )
    refresh = create_token(
        str(user_id),
        "refresh",
        dt.timedelta(days=settings.jwt_refresh_ttl_days),
        session_id=sid,
        extra={"jti": next_refresh_jti},
    )
    return access, refresh


async def resend_login_otp(
    session: AsyncSession, *, user_id: int, challenge_id: int
) -> OtpChallenge:
    """Resend a login code only while the account-wide lockout permits it."""
    user = (
        await session.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one_or_none()
    if user is None or not user.twofa_enabled:
        raise AuthError("two-factor not configured")
    failures = await _recent_failure_count(session, user.email)
    if failures >= MAX_FAILURES:
        await record_event(
            session,
            level="WARN",
            category="security",
            message="SMS resend blocked — account temporarily locked",
            ref=f"login_locked:{user.email}",
            payload={"email": user.email, "failures": failures},
        )
        await session.commit()
        raise RateLimitedError("account temporarily locked")
    return await otp_service.resend(
        session,
        challenge_id,
        user_id=user_id,
        expected_purpose="login",
    )


async def get_active_session(session: AsyncSession, sid: str) -> Session | None:
    """Return the session if active (not revoked, not expired), else None."""
    row = (await session.execute(select(Session).where(Session.sid == sid))).scalar_one_or_none()
    if row is None or row.revoked_at is not None or row.expires_at <= _now():
        return None
    return row


async def revoke_session(session: AsyncSession, sid: str) -> None:
    """Revoke a single session (logout)."""
    row = (await session.execute(select(Session).where(Session.sid == sid))).scalar_one_or_none()
    if row is not None and row.revoked_at is None:
        row.revoked_at = _now()


async def revoke_other_sessions(session: AsyncSession, user_id: int, keep_sid: str) -> int:
    """Revoke all of a user's sessions except keep_sid. Returns count revoked."""
    rows = (
        await session.execute(
            select(Session).where(
                Session.user_id == user_id,
                Session.sid != keep_sid,
                Session.revoked_at.is_(None),
            )
        )
    ).scalars()
    count = 0
    for row in rows:
        row.revoked_at = _now()
        count += 1
    return count


# --- Guarded two-factor settings changes -------------------------------------


def security_status(user: User) -> dict[str, object]:
    """Return the owner's 2FA state for the Settings UI (masked phone only)."""
    phone_hint = None
    if user.phone_encrypted is not None:
        phone = decrypt(user.phone_encrypted, get_settings().master_key)
        phone_hint = otp_service.phone_hint(phone)
    return {"twofa_enabled": user.twofa_enabled, "phone_hint": phone_hint}


async def _send_security_notice(
    config: NotifyConfig | None, phone: str, message: str
) -> SmsResult | None:
    """Best-effort SMS notice to a number about a security change.

    Independent of the alerts toggle. Never raises — the durable record is the
    security event; a failed notice must not roll back the change.
    """
    from app.notifier.gateway import NotifyLkGateway

    if config is None:
        return None
    gateway = NotifyLkGateway(config.user_id, config.api_key, config.sender_id)
    try:
        return await gateway.send(otp_service.normalize_phone(phone), message)
    finally:
        await gateway.close()


async def start_security_change(
    session: AsyncSession,
    user: User,
    *,
    action: SecurityAction,
    password: str,
    new_phone: str | None,
) -> OtpChallenge:
    """Re-authenticate with the password and send an OTP to the relevant number.

    Returns the otp-pending token bound to the created challenge. The password
    re-check means an open session (e.g. a stolen laptop) cannot flip 2FA
    without also knowing the password.
    """
    # Reload and lock the owner row so the failure-budget check, Argon2 verify,
    # and durable failure event are one serialized transaction.
    locked_user = await require_password_reauth(
        session,
        user,
        password,
        action=f"twofa_{action}",
        ref_prefix="twofa_reauth_fail",
    )

    purpose: otp_service.Purpose
    if action == "enable":
        if locked_user.twofa_enabled:
            raise TwoFactorError("two-factor is already enabled")
        if not new_phone:
            raise TwoFactorError("a mobile number is required to enable two-factor")
        purpose, target = "enable_2fa", new_phone
    elif action == "change_phone":
        if not locked_user.twofa_enabled:
            raise TwoFactorError("enable two-factor before changing the number")
        if not new_phone:
            raise TwoFactorError("a new mobile number is required")
        purpose, target = "change_phone", new_phone
    else:  # disable
        if not locked_user.twofa_enabled or locked_user.phone_encrypted is None:
            raise TwoFactorError("two-factor is not enabled")
        purpose = "disable_2fa"
        target = decrypt(locked_user.phone_encrypted, get_settings().master_key)

    try:
        challenge = await otp_service.start_challenge(
            session, user=locked_user, purpose=purpose, phone=target
        )
    except otp_service.OtpThrottled as exc:
        raise RateLimitedError(str(exc)) from exc
    except otp_service.OtpSendError as exc:
        raise TwoFactorError("could not send verification code") from exc

    return challenge


async def confirm_security_change(
    session: AsyncSession, user: User, challenge_id: int, code: str, *, current_sid: str
) -> str:
    """Verify the OTP and commit the pending 2FA change.

    Phone changes and disables revoke all other sessions and notify the previous
    number. Every outcome writes a `security` event.
    """
    # Use the same owner→challenge lock order as challenge creation, login OTP
    # verification, and resend. This serializes competing security changes and
    # ensures every state check observes the latest committed owner state.
    locked_user = (
        await session.execute(select(User).where(User.id == user.id).with_for_update())
    ).scalar_one_or_none()
    if locked_user is None:
        raise AuthError("account is no longer available")
    challenge = (
        await session.execute(select(OtpChallenge).where(OtpChallenge.id == challenge_id))
    ).scalar_one_or_none()
    if (
        challenge is None
        or challenge.user_id != locked_user.id
        or challenge.purpose
        not in {
            "enable_2fa",
            "disable_2fa",
            "change_phone",
        }
    ):
        raise TwoFactorError("invalid verification challenge")

    if challenge.purpose == "enable_2fa" and locked_user.twofa_enabled:
        raise TwoFactorError("two-factor is already enabled")
    if challenge.purpose in {"disable_2fa", "change_phone"} and not locked_user.twofa_enabled:
        raise TwoFactorError("two-factor is not enabled")
    if challenge.purpose == "disable_2fa" and (
        locked_user.phone_encrypted is None
        or otp_service.challenge_phone(challenge)
        != decrypt(locked_user.phone_encrypted, get_settings().master_key)
    ):
        raise TwoFactorError("verification challenge is no longer valid")

    try:
        await otp_service.verify(session, challenge_id, code)
    except (otp_service.OtpInvalid, otp_service.OtpLocked, otp_service.OtpExpired) as exc:
        raise AuthError(str(exc)) from exc

    old_phone = (
        decrypt(locked_user.phone_encrypted, get_settings().master_key)
        if locked_user.phone_encrypted
        else None
    )
    notice_config = (
        await get_notify_config(session)
        if challenge.purpose in {"change_phone", "disable_2fa"}
        else None
    )

    if challenge.purpose == "enable_2fa":
        locked_user.phone_encrypted = challenge.phone_encrypted
        locked_user.twofa_enabled = True
        message = "Two-factor authentication enabled."
        ref = "twofa_enabled"
    elif challenge.purpose == "change_phone":
        locked_user.phone_encrypted = challenge.phone_encrypted
        message = "Two-factor mobile number changed."
        ref = "twofa_phone_changed"
    else:  # disable_2fa
        locked_user.twofa_enabled = False
        message = "Two-factor authentication disabled — logins now use password only."
        ref = "twofa_disabled"

    await record_event(
        session,
        level="WARN" if challenge.purpose == "disable_2fa" else "INFO",
        category="security",
        message=message,
        ref=f"{ref}:{locked_user.email}",
        payload={"email": locked_user.email},
    )

    # Strengthen: phone change / disable invalidate every other session and warn
    # the previously-enrolled number.
    if challenge.purpose in {"change_phone", "disable_2fa"}:
        await revoke_other_sessions(session, locked_user.id, current_sid)
    await otp_service.invalidate_user_challenges(session, locked_user.id, except_id=challenge.id)
    # Commit the OTP consumption, security change, session revocations and
    # audit event atomically before the best-effort external notification.
    await session.commit()

    if challenge.purpose in {"change_phone", "disable_2fa"} and old_phone:
        notice = await _send_security_notice(
            notice_config,
            old_phone,
            f"CryptoPilot security alert: {message} If this wasn't you, "
            "sign in and rotate your credentials immediately.",
        )
        await record_event(
            session,
            level="INFO" if notice and notice.ok else "WARN",
            category="security",
            message="Previous phone security notice attempted",
            ref=f"twofa_notice:{locked_user.email}",
            sms_status="delivered" if notice and notice.ok else "failed",
            payload={"change": challenge.purpose},
        )
        await session.commit()

    return message
