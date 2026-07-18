"""Security primitives: Argon2id password hashing, JWT tokens, TOTP.

See docs/guidelines/SECURITY_GUIDELINES.md. Secrets are never logged; token
verification raises typed errors the API maps to 401.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()

TokenPurpose = Literal["access", "refresh", "totp_pending"]


class TokenError(Exception):
    """Raised when a JWT is invalid, expired, or has the wrong purpose."""


# --- Passwords ---------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash. Returns False on mismatch."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True if the hash was made with weaker params and should be upgraded."""
    return _hasher.check_needs_rehash(password_hash)


# --- JWT ---------------------------------------------------------------------


def create_token(
    subject: str,
    purpose: TokenPurpose,
    ttl: dt.timedelta,
    *,
    session_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT with subject, purpose, expiry and optional session id."""
    settings = get_settings()
    now = dt.datetime.now(dt.UTC)
    claims: dict[str, Any] = {
        "sub": subject,
        "purpose": purpose,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if session_id is not None:
        claims["sid"] = session_id
    if extra:
        claims.update(extra)
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str, *, expected_purpose: TokenPurpose) -> dict[str, Any]:
    """Decode and validate a JWT, enforcing the expected purpose.

    Raises TokenError on any failure (bad signature, expiry, wrong purpose).
    """
    settings = get_settings()
    try:
        claims: dict[str, Any] = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token expired") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("invalid token") from exc
    if claims.get("purpose") != expected_purpose:
        raise TokenError("wrong token purpose")
    return claims


# --- TOTP --------------------------------------------------------------------


def generate_totp_secret() -> str:
    """Generate a new base32 TOTP secret."""
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, email: str, issuer: str = "CryptoPilot") -> str:
    """Return an otpauth:// URI for authenticator-app enrolment."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str, *, valid_window: int = 1) -> bool:
    """Verify a 6-digit TOTP code, allowing ±1 step for clock skew."""
    cleaned = code.replace(" ", "").strip()
    if not cleaned.isdigit():
        return False
    return pyotp.TOTP(secret).verify(cleaned, valid_window=valid_window)
