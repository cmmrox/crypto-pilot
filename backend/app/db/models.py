"""SQLAlchemy models — the full schema from DATABASE_ARCHITECTURE.md.

All money is Decimal/numeric(20,8); all timestamps are timezone-aware UTC.
Secret material lives only in *_encrypted columns (AES-GCM).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IntPk


class User(Base):
    __tablename__ = "users"

    id: Mapped[IntPk]
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="owner", nullable=False)
    # SMS second factor. phone_encrypted holds the AES-GCM ciphertext of the
    # 2FA number; when twofa_enabled is false, login is password-only.
    phone_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    twofa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class OtpChallenge(Base):
    """A short-lived SMS one-time-password challenge.

    Codes are random, single-use and stored only as a keyed hash. A challenge is
    consumed on success and dies after max_attempts failures or expiry. The
    login step binds its otp_pending token to a specific challenge id so a token
    can never be replayed against a different challenge.
    """

    __tablename__ = "otp_challenges"
    __table_args__ = (
        Index("ix_otp_user_purpose_created", "user_id", "purpose", "created_at"),
        CheckConstraint(
            "purpose IN ('login', 'enable_2fa', 'disable_2fa', 'change_phone')",
            name="ck_otp_challenges_purpose",
        ),
        CheckConstraint("attempts >= 0", name="ck_otp_challenges_attempts"),
        CheckConstraint("max_attempts > 0", name="ck_otp_challenges_max_attempts"),
        CheckConstraint("send_count > 0", name="ck_otp_challenges_send_count"),
    )

    id: Mapped[IntPk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    # login | enable_2fa | disable_2fa | change_phone
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    # Target number for this challenge (AES-GCM); for change_phone/enable this is
    # the NEW number being proven, not necessarily the user's stored one.
    phone_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=5, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    consumed_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    last_sent_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    send_count: Mapped[int] = mapped_column(default=1, nullable=False)


class Session(Base):
    """A logged-in owner session; enables server-side revocation.

    Access tokens carry `sid`; every authenticated request checks the session is
    not revoked or expired (SECURITY_GUIDELINES.md).
    """

    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user", "user_id"),)

    id: Mapped[IntPk]
    sid: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    refresh_jti: Mapped[str | None] = mapped_column(String(32), nullable=True)
    expires_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AppSettings(Base):
    """Singleton configuration row (id is always 1)."""

    __tablename__ = "app_settings"

    id: Mapped[IntPk]
    active_environment: Mapped[str] = mapped_column(String(8), default="DEMO", nullable=False)
    active_strategy: Mapped[str] = mapped_column(
        String(64), default="trend_rider_v6_4h", nullable=False
    )
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    news_sources: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    news_time: Mapped[str] = mapped_column(String(5), default="06:30")
    news_provider: Mapped[str] = mapped_column(String(32), default="codex")
    updated_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)


class ApiCredential(Base):
    __tablename__ = "api_credentials"
    __table_args__ = (UniqueConstraint("environment", "service", name="uq_cred_env_service"),)

    id: Mapped[IntPk]
    environment: Mapped[str] = mapped_column(String(8), nullable=False)  # DEMO | LIVE
    service: Mapped[str] = mapped_column(String(32), nullable=False)  # binance|notifylk|codex
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Legacy compatibility only. New writes set this to NULL and lazy-migrate
    # any pre-upgrade plaintext value on first access.
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)


class BotRun(Base):
    __tablename__ = "bot_runs"

    id: Mapped[IntPk]
    started_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    stopped_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    environment: Mapped[str] = mapped_column(String(8), nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_release: Mapped[str] = mapped_column(String(32), default="legacy", nullable=False)
    strategy_interval: Mapped[str] = mapped_column(String(8), default="4h", nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("symbol", "interval", "open_time", name="uq_candle_key"),
        Index("ix_candles_symbol_interval_time", "symbol", "interval", "open_time"),
    )

    id: Mapped[IntPk]
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    interval: Mapped[str] = mapped_column(String(8), nullable=False)
    open_time: Mapped[dt.datetime] = mapped_column(nullable=False)
    open: Mapped[Decimal]
    high: Mapped[Decimal]
    low: Mapped[Decimal]
    close: Mapped[Decimal]
    volume: Mapped[Decimal]
    closed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_env_opened", "environment", "opened_at"),
        Index("ix_trades_side", "side"),
        Index("ix_trades_strategy", "strategy"),
    )

    id: Mapped[IntPk]
    opened_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    closed_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # LONG | SHORT
    entry_px: Mapped[Decimal]
    exit_px: Mapped[Decimal | None] = mapped_column(nullable=True)
    qty: Mapped[Decimal]
    remaining_qty: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    highest_high: Mapped[Decimal | None] = mapped_column(nullable=True)
    fees: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    funding: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    realized_pnl: Mapped[Decimal | None] = mapped_column(nullable=True)
    r_multiple: Mapped[Decimal | None] = mapped_column(nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_release: Mapped[str] = mapped_column(String(32), default="legacy", nullable=False)
    strategy_interval: Mapped[str] = mapped_column(String(8), default="4h", nullable=False)
    environment: Mapped[str] = mapped_column(String(8), nullable=False)
    bot_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("bot_runs.id"), nullable=True
    )

    orders: Mapped[list[Order]] = relationship(back_populates="trade")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[IntPk]
    binance_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    trade_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("trades.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(nullable=True)
    qty: Mapped[Decimal]
    filled_qty: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    avg_fill_px: Mapped[Decimal | None] = mapped_column(nullable=True)
    reduce_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    placed_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    filled_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    trade: Mapped[Trade | None] = relationship(back_populates="orders")


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"
    __table_args__ = (
        UniqueConstraint("environment", "ts", name="uq_equity_env_ts"),
        Index("ix_equity_env_ts", "environment", "ts"),
    )

    id: Mapped[IntPk]
    ts: Mapped[dt.datetime] = mapped_column(nullable=False)
    environment: Mapped[str] = mapped_column(String(8), nullable=False)
    balance: Mapped[Decimal]
    unrealized_pnl: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    month_to_date_pnl: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    sleeve_month_pnl: Mapped[Decimal] = mapped_column(default=Decimal("0"))


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_ts", "ts"),
        Index("ix_events_category_ts", "category", "ts"),
        Index("ix_events_level_ts", "level", "ts"),
    )

    id: Mapped[IntPk]
    ts: Mapped[dt.datetime] = mapped_column(nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False)  # INFO|WARN|ERROR
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    sms_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    ref: Mapped[str | None] = mapped_column(String(64), nullable=True)


class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[IntPk]
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class Briefing(Base):
    __tablename__ = "briefings"

    id: Mapped[IntPk]
    briefing_date: Mapped[dt.date] = mapped_column(unique=True, nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    bullets: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    sentiment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    generated_at: Mapped[dt.datetime] = mapped_column(nullable=False)


class WithdrawalMark(Base):
    __tablename__ = "withdrawal_marks"

    id: Mapped[IntPk]
    month: Mapped[str] = mapped_column(String(7), unique=True, nullable=False)  # YYYY-MM
    amount: Mapped[Decimal]
    marked_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    marked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


__all__ = [
    "ApiCredential",
    "AppSettings",
    "BotRun",
    "Briefing",
    "Candle",
    "EquitySnapshot",
    "Event",
    "NewsItem",
    "Order",
    "OtpChallenge",
    "Session",
    "Trade",
    "User",
    "WithdrawalMark",
]
