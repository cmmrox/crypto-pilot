"""Security primitives: Argon2id password hashing, JWT tokens, SMS OTP codes.

See docs/guidelines/SECURITY_GUIDELINES.md. Secrets are never logged; token
verification raises typed errors the API maps to 401.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets
import uuid
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()

TokenPurpose = Literal["access", "refresh", "otp_pending"]

OTP_LENGTH = 6


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


# --- SMS OTP -----------------------------------------------------------------


def generate_otp() -> str:
    """Return a cryptographically-random 6-digit numeric code (zero-padded)."""
    return f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"


def _otp_key() -> bytes:
    """Derive an HMAC key for OTP hashing from the master key.

    The master key never leaves the environment, so a passive reader of the
    otp_challenges table cannot recover live codes from their stored hashes.
    """
    return hashlib.sha256(get_settings().master_key.encode("utf-8")).digest()


def hash_otp(code: str) -> str:
    """Return the keyed HMAC-SHA256 hash of an OTP code (hex)."""
    return hmac.new(_otp_key(), code.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_otp_hash(code: str, code_hash: str) -> bool:
    """Timing-safe check of a candidate code against a stored hash."""
    cleaned = code.replace(" ", "").strip()
    if not cleaned.isdigit():
        return False
    return hmac.compare_digest(hash_otp(cleaned), code_hash)
