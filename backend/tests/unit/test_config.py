"""Unit tests for settings validation (QA-0)."""

from __future__ import annotations

import pytest
from app.core.config import Settings
from pydantic import ValidationError

_BASE_ENV = {
    "CP_DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
    "CP_MASTER_KEY": "a" * 44,
    "CP_JWT_SECRET": "b" * 44,
}


def test_valid_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.app_name == "CryptoPilot"
    assert not s.is_production


def test_placeholder_secret_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("CP_JWT_SECRET", "changeme".ljust(32, "x"))
    monkeypatch.setenv("CP_MASTER_KEY", "changeme")  # too short AND placeholder
    with pytest.raises(ValidationError):
        Settings()


def test_missing_required_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CP_DATABASE_URL", raising=False)
    monkeypatch.delenv("CP_MASTER_KEY", raising=False)
    monkeypatch.delenv("CP_JWT_SECRET", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("CP_ENVIRONMENT", "production")
    assert Settings().is_production
