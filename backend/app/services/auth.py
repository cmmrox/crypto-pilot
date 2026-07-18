"""Authentication service: login, TOTP, sessions, rate limiting.

Rate limiting is DB-backed (recent failed-login security events) so it survives
restarts and is auditable. Sessions are server-side for real revocation.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import decrypt
from app.core.security import (
    create_token,
    hash_password,
    needs_rehash,
    verify_password,
    verify_totp,
)
from app.db.models import Event, Session, User
from app.services.events import record_event, record_event_committed

# Lockout policy
MAX_FAILURES = 5
LOCKOUT_WINDOW = dt.timedelta(minutes=15)
TOTP_PENDING_TTL = dt.timedelta(minutes=5)


class AuthError(Exception):
    """Base authentication failure (maps to 401)."""


class RateLimitedError(Exception):
    """Too many recent failures (maps to 429)."""


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


async def authenticate_password(
    session: AsyncSession, email: str, password: str, *, user_agent: str | None = None
) -> str:
    """Verify email+password. Returns a short-lived TOTP-pending token.

    Raises RateLimitedError when locked out, AuthError on bad credentials.
    """
    failures = await _recent_failure_count(session, email)
    if failures >= MAX_FAILURES:
        # Autonomous commit: the failure/lockout audit trail must survive the
        # request rollback that follows raising below.
        await record_event_committed(
            level="WARN",
            category="security",
            message="Login blocked — too many recent failures",
            ref=f"login_locked:{email}",
            payload={"email": email, "failures": failures},
        )
        raise RateLimitedError("account temporarily locked")

    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    ok = user is not None and verify_password(password, user.password_hash)
    if not ok or user is None:
        await record_event_committed(
            level="WARN",
            category="security",
            message="Failed login attempt",
            ref=f"login_fail:{email}",
            payload={"email": email, "user_agent": user_agent},
        )
        raise AuthError("invalid email or password")

    # Opportunistic password rehash if params strengthened
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    await record_event(
        session,
        level="INFO",
        category="security",
        message="Password verified — awaiting TOTP",
        ref=f"login_pw_ok:{email}",
        payload={"email": email},
    )
    return create_token(str(user.id), "totp_pending", TOTP_PENDING_TTL)


async def verify_totp_and_issue(
    session: AsyncSession, user_id: int, code: str, *, user_agent: str | None = None
) -> tuple[str, str]:
    """Verify a TOTP code and issue access + refresh tokens, creating a session."""
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.totp_enabled or user.totp_secret_encrypted is None:
        raise AuthError("two-factor not configured")

    secret = decrypt(user.totp_secret_encrypted, get_settings().master_key)
    if not verify_totp(secret, code):
        await record_event_committed(
            level="WARN",
            category="security",
            message="Failed TOTP verification",
            ref=f"login_fail:{user.email}",
            payload={"email": user.email},
        )
        raise AuthError("invalid authenticator code")

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


async def refresh_access(session: AsyncSession, sid: str, refresh_jti: str, user_id: int) -> str:
    """Issue a fresh access token if the session is valid and not revoked."""
    row = (await session.execute(select(Session).where(Session.sid == sid))).scalar_one_or_none()
    if (
        row is None
        or row.revoked_at is not None
        or row.expires_at <= _now()
        or row.refresh_jti != refresh_jti
        or row.user_id != user_id
    ):
        raise AuthError("session is no longer valid")
    row.last_used_at = _now()
    return create_token(
        str(user_id),
        "access",
        dt.timedelta(minutes=get_settings().jwt_access_ttl_minutes),
        session_id=sid,
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
