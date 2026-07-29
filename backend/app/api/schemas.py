"""Pydantic request/response models for the API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

# notify.lk owner numbers use the documented Sri Lankan international form.
PHONE_PATTERN = r"^94[0-9]{9}$"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    """Password-step outcome.

    mode="tokens" → 2FA is off and access/refresh are already issued.
    mode="otp"    → an SMS code was sent; complete via /api/auth/otp/verify with
    the otp_token as the bearer credential.
    """

    mode: Literal["tokens", "otp"]
    access_token: str | None = None
    refresh_token: str | None = None
    otp_token: str | None = None
    phone_hint: str | None = None


class OtpVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# --- Security settings (2FA) ---


class SecurityStatusOut(BaseModel):
    twofa_enabled: bool
    phone_hint: str | None


class SecurityChangeStart(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    action: Literal["enable", "disable", "change_phone"]
    new_phone: str | None = Field(default=None, pattern=PHONE_PATTERN)


class SecurityChangeStartOut(BaseModel):
    challenge_id: int
    phone_hint: str | None


class SecurityChangeConfirm(BaseModel):
    challenge_id: int = Field(gt=0)
    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class DevOtpOut(BaseModel):
    """TEST/E2E ONLY response for the gated dev-code endpoint."""

    code: str


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    email: EmailStr
    role: str


class MessageResponse(BaseModel):
    message: str


# --- Events ---


class EventOut(BaseModel):
    id: int
    ts: str
    level: str
    category: str
    message: str
    payload_json: dict[str, object]
    sms_status: str | None
    ref: str | None


# --- Market / connection ---


class CandleOut(BaseModel):
    open_time: str
    open: str
    high: str
    low: str
    close: str
    volume: str


class MarketStatus(BaseModel):
    symbol: str
    interval: str
    environment: str
    candles_stored: int
    latest_open_time: str | None
    gaps: int
    next_close_utc: str
    seconds_to_next_close: float
    clock_drift_ms: int | None
    exchange_reachable: bool


# --- Credentials ---


class CredentialIn(BaseModel):
    environment: str = Field(pattern="^(DEMO|LIVE)$")
    service: Literal["binance"]
    api_key: str = Field(min_length=1, max_length=512)
    api_secret: str = Field(min_length=1, max_length=1024)
    current_password: str = Field(min_length=1, max_length=256)


class CredentialStatusOut(BaseModel):
    service: str
    environment: str
    configured: bool
    key_hint: str | None


class LiveReadinessOut(BaseModel):
    ready: bool
    ip_restricted: bool
    reading_enabled: bool
    futures_enabled: bool
    withdrawals_disabled: bool
    unrelated_permissions_disabled: bool
    one_way_mode: bool
    single_asset_mode: bool
    open_position_count: int
    open_order_count: int
    btcusdt_margin_type: str | None
    btcusdt_leverage: int | None
    issues: list[str]


class ConnectionTestOut(BaseModel):
    ok: bool
    detail: str
    live_readiness: LiveReadinessOut | None = None
