#!/usr/bin/env python3
"""Create or verify a backup HMAC without placing key material in process argv."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import os
from pathlib import Path

_CONTEXT = b"cryptopilot-backup-auth-v1"
_CHUNK_SIZE = 1024 * 1024


def _mac_key() -> bytes:
    encoded = os.environ.get("CP_MASTER_KEY", "")
    try:
        master = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise SystemExit("CP_MASTER_KEY must be valid base64") from exc
    if len(master) != 32:
        raise SystemExit("CP_MASTER_KEY must decode to exactly 32 bytes")
    return hmac.new(master, _CONTEXT, hashlib.sha256).digest()


def _digest(path: Path) -> bytes:
    digest = hmac.new(_mac_key(), digestmod=hashlib.sha256)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.digest()


def create(ciphertext: Path, mac_path: Path) -> None:
    temporary = mac_path.with_name(f".{mac_path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_bytes(_digest(ciphertext))
        temporary.chmod(0o600)
        temporary.replace(mac_path)
    finally:
        temporary.unlink(missing_ok=True)


def verify(ciphertext: Path, mac_path: Path) -> None:
    try:
        expected = mac_path.read_bytes()
    except FileNotFoundError as exc:
        raise SystemExit(f"backup authentication file is missing: {mac_path}") from exc
    if not hmac.compare_digest(_digest(ciphertext), expected):
        raise SystemExit("backup authentication failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("create", "verify"))
    parser.add_argument("ciphertext", type=Path)
    parser.add_argument("mac", type=Path)
    args = parser.parse_args()
    if args.mode == "create":
        create(args.ciphertext, args.mac)
    else:
        verify(args.ciphertext, args.mac)


if __name__ == "__main__":
    main()
