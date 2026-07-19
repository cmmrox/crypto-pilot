"""Unit tests for security primitives (QA-1)."""

from __future__ import annotations

import datetime as dt

import pytest
from app.core.security import (
    TokenError,
    create_token,
    decode_token,
    generate_otp,
    hash_otp,
    hash_password,
    verify_otp_hash,
    verify_password,
)

_ENV = {
    "CP_DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
    "CP_MASTER_KEY": "a" * 44,
    "CP_JWT_SECRET": "b" * 44,
}


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _ENV.items():
        monkeypatch.setenv(k, v)
    from app.core.config import get_settings

    get_settings.cache_clear()


def test_password_hash_and_verify() -> None:
    h = hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong", h)


def test_password_verify_bad_hash_is_false() -> None:
    assert not verify_password("x", "not-a-valid-argon2-hash")


def test_token_round_trip() -> None:
    token = create_token("42", "access", dt.timedelta(minutes=5), session_id="sid1")
    claims = decode_token(token, expected_purpose="access")
    assert claims["sub"] == "42"
    assert claims["sid"] == "sid1"
    assert claims["purpose"] == "access"


def test_token_wrong_purpose_rejected() -> None:
    token = create_token("42", "refresh", dt.timedelta(minutes=5))
    with pytest.raises(TokenError):
        decode_token(token, expected_purpose="access")


def test_token_expired_rejected() -> None:
    token = create_token("42", "access", dt.timedelta(seconds=-1))
    with pytest.raises(TokenError):
        decode_token(token, expected_purpose="access")


def test_token_tampered_rejected() -> None:
    token = create_token("42", "access", dt.timedelta(minutes=5))
    tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
    with pytest.raises(TokenError):
        decode_token(tampered, expected_purpose="access")


def test_generate_otp_is_six_digits() -> None:
    for _ in range(50):
        code = generate_otp()
        assert len(code) == 6
        assert code.isdigit()


def test_otp_hash_verifies() -> None:
    code = generate_otp()
    h = hash_otp(code)
    assert verify_otp_hash(code, h)
    assert not verify_otp_hash("000000" if code != "000000" else "111111", h)


def test_otp_hash_is_not_reversible_plaintext() -> None:
    code = "123456"
    assert code not in hash_otp(code)


def test_otp_verify_rejects_non_numeric() -> None:
    assert not verify_otp_hash("abcdef", hash_otp("123456"))


def test_otp_verify_tolerates_whitespace() -> None:
    code = "123456"
    assert verify_otp_hash(" 123456 ", hash_otp(code))
