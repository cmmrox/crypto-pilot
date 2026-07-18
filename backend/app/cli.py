"""Operational CLI: provision the owner account.

Usage:
    python -m app.cli create-owner --email you@example.com --password '...' [--totp-secret BASE32]

Prints the otpauth:// enrolment URI. If --totp-secret is omitted, a new secret is
generated. Idempotent-ish: refuses to overwrite an existing owner unless --force.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.crypto import encrypt
from app.core.security import (
    generate_totp_secret,
    hash_password,
    totp_provisioning_uri,
)
from app.db.models import User
from app.db.session import get_sessionmaker


async def _create_owner(email: str, password: str, totp_secret: str | None, force: bool) -> int:
    secret = totp_secret or generate_totp_secret()
    async with get_sessionmaker()() as session:
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is not None and not force:
            print(f"Owner {email} already exists (use --force to reset).", file=sys.stderr)
            return 1
        enc_secret = encrypt(secret, get_settings().master_key)
        if existing is None:
            session.add(
                User(
                    email=email,
                    password_hash=hash_password(password),
                    role="owner",
                    totp_secret_encrypted=enc_secret,
                    totp_enabled=True,
                )
            )
        else:
            existing.password_hash = hash_password(password)
            existing.totp_secret_encrypted = enc_secret
            existing.totp_enabled = True
        await session.commit()

    print("Owner provisioned.")
    print(f"  Email:       {email}")
    print(f"  TOTP secret: {secret}")
    print(f"  Enrol URI:   {totp_provisioning_uri(secret, email)}")
    print("Scan the URI in an authenticator app. Keep the secret private.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-owner", help="Create or reset the owner account")
    create.add_argument("--email", required=True)
    create.add_argument("--password", required=True)
    create.add_argument("--totp-secret", default=None, help="Base32 secret (else generated)")
    create.add_argument("--force", action="store_true", help="Overwrite an existing owner")
    args = parser.parse_args(argv)

    if args.command == "create-owner":
        return asyncio.run(
            _create_owner(args.email, args.password, args.totp_secret, args.force)
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
