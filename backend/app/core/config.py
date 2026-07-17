"""Application configuration via environment variables (pydantic-settings).

All configuration enters here — no hardcoded URLs, keys, or magic numbers elsewhere.
Secrets are read from the environment only; see docs/guidelines/SECURITY_GUIDELINES.md.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings. Instantiated once via get_settings()."""

    model_config = SettingsConfigDict(
        env_prefix="CP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "CryptoPilot"
    version: str = "0.1.0"
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = False

    # --- Database ---
    database_url: PostgresDsn = Field(
        default=...,
        description="Async PostgreSQL DSN, e.g. postgresql+asyncpg://user:pass@host/db",
    )

    # --- Security ---
    master_key: str = Field(
        default=...,
        min_length=32,
        description="Base64 32-byte key for AES-GCM encryption of secrets at rest.",
    )
    jwt_secret: str = Field(default=..., min_length=32)
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 7
    argon2_time_cost: int = 3
    argon2_memory_cost_kib: int = 65536
    argon2_parallelism: int = 4

    # --- CORS / frontend ---
    frontend_origin: str = "http://localhost:5173"

    # --- Logging ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True

    @field_validator("master_key", "jwt_secret")
    @classmethod
    def _not_placeholder(cls, v: str) -> str:
        if v.strip().lower() in {"changeme", "change-me", "todo", ""}:
            raise ValueError("secret must be set to a real value, not a placeholder")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton."""
    return Settings()  # values come from the environment
