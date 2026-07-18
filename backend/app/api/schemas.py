"""Pydantic request/response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    """Returned after a valid password; TOTP still required."""

    totp_token: str
    totp_required: bool = True


class TotpRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


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
    service: str = Field(pattern="^(binance|notifylk|codex)$")
    api_key: str = Field(min_length=1, max_length=512)
    api_secret: str = Field(min_length=1, max_length=1024)


class CredentialStatusOut(BaseModel):
    service: str
    environment: str
    configured: bool
    key_hint: str | None


class ConnectionTestOut(BaseModel):
    ok: bool
    detail: str
