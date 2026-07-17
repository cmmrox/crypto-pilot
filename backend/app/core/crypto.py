"""AES-GCM encryption for secrets at rest (BSD §13, SECURITY_GUIDELINES.md).

The master key is provided only via the environment. Ciphertext is stored as
base64(nonce || ciphertext_with_tag). Never log plaintext or key material.
"""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12


class DecryptionError(Exception):
    """Raised when ciphertext cannot be authenticated/decrypted."""


def _load_key(master_key_b64: str) -> bytes:
    """Decode and validate a 32-byte AES-256 key from base64."""
    try:
        key = base64.b64decode(master_key_b64, validate=True)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise DecryptionError("master key is not valid base64") from exc
    if len(key) != 32:
        raise DecryptionError("master key must decode to exactly 32 bytes (AES-256)")
    return key


def encrypt(plaintext: str, master_key_b64: str) -> str:
    """Encrypt a UTF-8 string, returning base64(nonce || ciphertext||tag)."""
    key = _load_key(master_key_b64)
    nonce = os.urandom(_NONCE_BYTES)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt(token_b64: str, master_key_b64: str) -> str:
    """Decrypt base64(nonce || ciphertext||tag) back to the original string."""
    key = _load_key(master_key_b64)
    try:
        raw = base64.b64decode(token_b64, validate=True)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise DecryptionError("ciphertext is not valid base64") from exc
    if len(raw) <= _NONCE_BYTES:
        raise DecryptionError("ciphertext too short")
    nonce, ct = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
    except InvalidTag as exc:
        raise DecryptionError("authentication failed — wrong key or tampered data") from exc


def generate_master_key() -> str:
    """Generate a fresh base64 32-byte key (for setup/tests)."""
    return base64.b64encode(os.urandom(32)).decode("ascii")
