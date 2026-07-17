"""Unit tests for AES-GCM secret encryption (QA-0)."""

from __future__ import annotations

import base64

import pytest
from app.core.crypto import DecryptionError, decrypt, encrypt, generate_master_key


def test_round_trip() -> None:
    key = generate_master_key()
    secret = "binance-demo-secret-abc123"
    assert decrypt(encrypt(secret, key), key) == secret


def test_ciphertext_differs_each_call() -> None:
    key = generate_master_key()
    a = encrypt("same", key)
    b = encrypt("same", key)
    assert a != b  # random nonce per encryption


def test_wrong_key_fails_authentication() -> None:
    token = encrypt("secret", generate_master_key())
    with pytest.raises(DecryptionError):
        decrypt(token, generate_master_key())


def test_tampered_ciphertext_fails() -> None:
    key = generate_master_key()
    token = encrypt("secret", key)
    raw = bytearray(base64.b64decode(token))
    raw[-1] ^= 0x01  # flip a tag bit
    tampered = base64.b64encode(bytes(raw)).decode()
    with pytest.raises(DecryptionError):
        decrypt(tampered, key)


def test_bad_key_length_rejected() -> None:
    short_key = base64.b64encode(b"tooshort").decode()
    with pytest.raises(DecryptionError):
        encrypt("x", short_key)


def test_unicode_secret() -> None:
    key = generate_master_key()
    secret = "sender-id-🔐-Ñ"
    assert decrypt(encrypt(secret, key), key) == secret
