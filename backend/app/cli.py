"""Operational CLI: provision the owner account and manage the SMS second factor.

Usage:
    python -m app.cli create-owner --email you@example.com --password '...' \
        [--phone 9471XXXXXXX]
    python -m app.cli set-phone --email you@example.com --phone 9471XXXXXXX
    python -m app.cli reset-2fa --email you@example.com

`create-owner` with --phone enables SMS 2FA immediately; without it the owner is
created with 2FA off and enables it from Settings. `reset-2fa` is the break-glass
path for a lost phone (requires shell access to the host).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import encrypt
from app.core.security import hash_password
from app.db.models import Event, Session, User
from app.db.session import get_sessionmaker
from app.services.notify_config import get_notify_config
from app.services.otp import invalidate_user_challenges, normalize_phone


def _normalize_phone(phone: str) -> str:
    try:
        return normalize_phone(phone)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


async def _record_security(
    session: AsyncSession, message: str, ref: str, email: str
) -> None:
    session.add(
        Event(
            ts=dt.datetime.now(dt.UTC),
            level="WARN",
            category="security",
            message=message,
            payload_json={"email": email},
            ref=ref,
        )
    )


async def _create_owner(email: str, password: str, phone: str | None, force: bool) -> int:
    async with get_sessionmaker()() as session:
        if (
            phone is not None
            and await get_notify_config(session) is None
            and not get_settings().otp_test_mode
        ):
            print(
                "notify.lk is not configured; create the owner without --phone, "
                "configure SMS in Settings, then enable 2FA.",
                file=sys.stderr,
            )
            return 1
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is not None and not force:
            print(f"Owner {email} already exists (use --force to reset).", file=sys.stderr)
            return 1
        enc_phone = (
            encrypt(_normalize_phone(phone), get_settings().master_key) if phone else None
        )
        twofa = phone is not None
        if existing is None:
            owner = User(
                email=email,
                password_hash=hash_password(password),
                role="owner",
                phone_encrypted=enc_phone,
                twofa_enabled=twofa,
            )
            session.add(owner)
            await session.flush()
            await _record_security(
                session, "Owner provisioned via CLI", f"owner_created:{email}", email
            )
        else:
            existing.password_hash = hash_password(password)
            existing.phone_encrypted = enc_phone
            existing.twofa_enabled = twofa
            sessions = (
                await session.execute(
                    select(Session).where(
                        Session.user_id == existing.id,
                        Session.revoked_at.is_(None),
                    )
                )
            ).scalars()
            for active_session in sessions:
                active_session.revoked_at = dt.datetime.now(dt.UTC)
            await invalidate_user_challenges(session, existing.id)
            await _record_security(
                session,
                "Owner credentials reset via CLI",
                f"owner_reset:{email}",
                email,
            )
        await session.commit()

    print("Owner provisioned.")
    print(f"  Email:          {email}")
    print(f"  Two-factor SMS: {'enabled' if phone else 'disabled (enable in Settings)'}")
    if phone:
        print(f"  Phone:          ···· {_normalize_phone(phone)[-4:]}")
    return 0


async def _set_phone(email: str, phone: str) -> int:
    async with get_sessionmaker()() as session:
        if await get_notify_config(session) is None:
            print(
                "notify.lk is not configured; refusing to enable SMS 2FA.",
                file=sys.stderr,
            )
            return 1
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            print(f"No owner with email {email}.", file=sys.stderr)
            return 1
        user.phone_encrypted = encrypt(_normalize_phone(phone), get_settings().master_key)
        user.twofa_enabled = True
        sessions = (
            await session.execute(
                select(Session).where(
                    Session.user_id == user.id,
                    Session.revoked_at.is_(None),
                )
            )
        ).scalars()
        for active_session in sessions:
            active_session.revoked_at = dt.datetime.now(dt.UTC)
        await invalidate_user_challenges(session, user.id)
        await _record_security(
            session, "2FA phone set via CLI", f"twofa_phone_changed:{email}", email
        )
        await session.commit()
    print(f"Two-factor SMS enabled for {email} (···· {_normalize_phone(phone)[-4:]}).")
    return 0


async def _reset_2fa(email: str) -> int:
    async with get_sessionmaker()() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            print(f"No owner with email {email}.", file=sys.stderr)
            return 1
        user.twofa_enabled = False
        user.phone_encrypted = None
        sessions = (
            await session.execute(
                select(Session).where(
                    Session.user_id == user.id,
                    Session.revoked_at.is_(None),
                )
            )
        ).scalars()
        for active_session in sessions:
            active_session.revoked_at = dt.datetime.now(dt.UTC)
        await invalidate_user_challenges(session, user.id)
        await _record_security(
            session, "2FA reset via CLI break-glass", f"twofa_disabled:{email}", email
        )
        await session.commit()
    print(f"Two-factor reset for {email}. Login is now password-only until re-enabled.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-owner", help="Create or reset the owner account")
    create.add_argument("--email", required=True)
    create.add_argument("--password", required=True)
    create.add_argument(
        "--phone",
        default=None,
        type=_normalize_phone,
        help="Enrol this 94XXXXXXXXX number for SMS 2FA",
    )
    create.add_argument("--force", action="store_true", help="Overwrite an existing owner")

    setp = sub.add_parser("set-phone", help="Set the 2FA number and enable SMS 2FA")
    setp.add_argument("--email", required=True)
    setp.add_argument("--phone", required=True, type=_normalize_phone)

    reset = sub.add_parser("reset-2fa", help="Break-glass: disable 2FA and clear the number")
    reset.add_argument("--email", required=True)

    args = parser.parse_args(argv)

    if args.command == "create-owner":
        return asyncio.run(
            _create_owner(args.email, args.password, args.phone, args.force)
        )
    if args.command == "set-phone":
        return asyncio.run(_set_phone(args.email, args.phone))
    if args.command == "reset-2fa":
        return asyncio.run(_reset_2fa(args.email))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
