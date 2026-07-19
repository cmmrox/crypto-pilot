"""Application configuration via environment variables (pydantic-settings).

All configuration enters here — no hardcoded URLs, keys, or magic numbers elsewhere.
Secrets are read from the environment only; see docs/guidelines/SECURITY_GUIDELINES.md.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator, model_validator
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
    # TEST/E2E ONLY: when true, SMS OTP codes are captured for retrieval via the
    # /api/auth/otp/dev-code endpoint instead of being trusted to real delivery.
    # Must never be enabled in production — the endpoint 404s unless this is set.
    otp_test_mode: bool = False
    # E2E suites reuse one owner and may exercise more than five auth flows.
    # This switch is rejected outside CP_ENVIRONMENT=test.
    otp_test_disable_throttle: bool = False
    # Stage-12 operational gates. Both must be explicitly enabled only after
    # the Stage-11 soak/sign-off and independent Binance key-permission review.
    live_trading_approved: bool = False
    live_key_permissions_verified: bool = False

    # --- CORS / frontend ---
    frontend_origin: str = "http://localhost:5173"

    # --- Codex (news LLM) ---
    codex_home: str = "/data/codex"  # persisted auth dir (CODEX_HOME)
    news_model: str = "gpt-5.5"

    # --- Logging ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True

    @field_validator("master_key", "jwt_secret")
    @classmethod
    def _not_placeholder(cls, v: str) -> str:
        if v.strip().lower() in {"changeme", "change-me", "todo", ""}:
            raise ValueError("secret must be set to a real value, not a placeholder")
        return v

    @model_validator(mode="after")
    def _test_otp_only_in_test_environment(self) -> Settings:
        if (self.otp_test_mode or self.otp_test_disable_throttle) and self.environment != "test":
            raise ValueError("OTP test controls are permitted only when CP_ENVIRONMENT=test")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton."""
    return Settings()  # values come from the environment
