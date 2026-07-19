"""Service-level tests for the OTP challenge lifecycle (QA-1).

Uses a real DB session (test mode captures codes in-process) to exercise expiry,
attempt limits and the resend cooldown directly, without the HTTP layer.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os

import pytest
from app.core.crypto import encrypt
from app.core.security import hash_password
from app.db.models import User
from app.services import otp as otp_service
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

PHONE = "94711234567"


async def _make_user(session: object) -> User:
    import os

    user = User(
        email="svc@example.com",
        password_hash=hash_password("pw"),
        role="owner",
        phone_encrypted=encrypt(PHONE, os.environ["CP_MASTER_KEY"]),
        twofa_enabled=True,
    )
    session.add(user)  # type: ignore[attr-defined]
    await session.flush()  # type: ignore[attr-defined]
    return user


@pytest.mark.asyncio
async def test_start_and_verify(db_session: object) -> None:
    import os

    os.environ["CP_OTP_TEST_MODE"] = "1"
    from app.core.config import get_settings

    get_settings.cache_clear()

    user = await _make_user(db_session)
    challenge = await otp_service.start_challenge(
        db_session, user=user, purpose="login", phone=PHONE
    )
    code = otp_service._TEST_CODES[otp_service.normalize_phone(PHONE)]
    verified = await otp_service.verify(db_session, challenge.id, code)
    assert verified.consumed_at is not None


@pytest.mark.asyncio
async def test_expired_challenge_rejected(db_session: object) -> None:
    import os

    os.environ["CP_OTP_TEST_MODE"] = "1"
    from app.core.config import get_settings

    get_settings.cache_clear()

    user = await _make_user(db_session)
    challenge = await otp_service.start_challenge(
        db_session, user=user, purpose="login", phone=PHONE
    )
    challenge.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    await db_session.flush()  # type: ignore[attr-defined]
    with pytest.raises(otp_service.OtpExpired):
        await otp_service.verify(db_session, challenge.id, "000000")


@pytest.mark.asyncio
async def test_attempts_exhausted_locks(db_session: object) -> None:
    import os

    os.environ["CP_OTP_TEST_MODE"] = "1"
    from app.core.config import get_settings

    get_settings.cache_clear()

    user = await _make_user(db_session)
    challenge = await otp_service.start_challenge(
        db_session, user=user, purpose="login", phone=PHONE
    )
    for _ in range(otp_service.MAX_ATTEMPTS - 1):
        with pytest.raises(otp_service.OtpInvalid):
            await otp_service.verify(db_session, challenge.id, "000000")
    with pytest.raises(otp_service.OtpLocked):
        await otp_service.verify(db_session, challenge.id, "000000")


@pytest.mark.asyncio
async def test_resend_cooldown_blocks(db_session: object) -> None:
    import os

    os.environ["CP_OTP_TEST_MODE"] = "1"
    from app.core.config import get_settings

    get_settings.cache_clear()

    user = await _make_user(db_session)
    challenge = await otp_service.start_challenge(
        db_session, user=user, purpose="login", phone=PHONE
    )
    with pytest.raises(otp_service.OtpThrottled):
        await otp_service.resend(
            db_session,
            challenge.id,
            user_id=user.id,
            expected_purpose="login",
        )


@pytest.mark.asyncio
async def test_resend_preserves_lifetime_attempt_budget(db_session: object) -> None:
    user = await _make_user(db_session)
    challenge = await otp_service.start_challenge(
        db_session, user=user, purpose="login", phone=PHONE
    )
    for _ in range(2):
        with pytest.raises(otp_service.OtpInvalid):
            await otp_service.verify(db_session, challenge.id, "000000")

    challenge.last_sent_at = (
        dt.datetime.now(dt.UTC) - otp_service.RESEND_COOLDOWN - dt.timedelta(seconds=1)
    )
    await db_session.commit()  # type: ignore[attr-defined]
    resent = await otp_service.resend(
        db_session,
        challenge.id,
        user_id=user.id,
        expected_purpose="login",
    )
    assert resent.attempts == 2

    for _ in range(otp_service.MAX_ATTEMPTS - 3):
        with pytest.raises(otp_service.OtpInvalid):
            await otp_service.verify(db_session, challenge.id, "000000")
    with pytest.raises(otp_service.OtpLocked):
        await otp_service.verify(db_session, challenge.id, "000000")

    challenge.last_sent_at = (
        dt.datetime.now(dt.UTC) - otp_service.RESEND_COOLDOWN - dt.timedelta(seconds=1)
    )
    await db_session.commit()  # type: ignore[attr-defined]
    with pytest.raises(otp_service.OtpLocked):
        await otp_service.resend(
            db_session,
            challenge.id,
            user_id=user.id,
            expected_purpose="login",
        )


@pytest.mark.asyncio
async def test_parallel_resends_share_atomic_hourly_cap(db_session: object) -> None:
    user = await _make_user(db_session)
    challenges = []
    for _ in range(otp_service.MAX_SENDS_PER_HOUR - 1):
        challenges.append(
            await otp_service.start_challenge(db_session, user=user, purpose="login", phone=PHONE)
        )
    old = dt.datetime.now(dt.UTC) - otp_service.RESEND_COOLDOWN - dt.timedelta(seconds=1)
    for challenge in challenges[:2]:
        challenge.last_sent_at = old
    await db_session.commit()  # type: ignore[attr-defined]

    engine = create_async_engine(os.environ["CP_DATABASE_URL"])

    async def resend(challenge_id: int) -> object:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            try:
                return await otp_service.resend(
                    session,
                    challenge_id,
                    user_id=user.id,
                    expected_purpose="login",
                )
            except Exception as exc:
                return exc

    results = await asyncio.gather(
        resend(challenges[0].id),
        resend(challenges[1].id),
    )
    await engine.dispose()
    assert sum(isinstance(result, otp_service.OtpChallenge) for result in results) == 1
    assert sum(isinstance(result, otp_service.OtpThrottled) for result in results) == 1
