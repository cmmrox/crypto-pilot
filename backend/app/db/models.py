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
    totp_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AppSettings(Base):
    """Singleton configuration row (id is always 1)."""

    __tablename__ = "app_settings"

    id: Mapped[IntPk]
    active_environment: Mapped[str] = mapped_column(String(8), default="DEMO", nullable=False)
    active_strategy: Mapped[str] = mapped_column(
        String(64), default="trend_rider_v6", nullable=False
    )
    risk_pct: Mapped[Decimal] = mapped_column(default=Decimal("2"))
    sleeve_weight_pct: Mapped[Decimal] = mapped_column(default=Decimal("75"))
    sleeve_vol_target: Mapped[Decimal] = mapped_column(default=Decimal("40"))
    leverage_cap: Mapped[Decimal] = mapped_column(default=Decimal("3"))
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
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[IntPk]
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    class_path: Mapped[str] = mapped_column(String(255), nullable=False)
    params_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    validated_release: Mapped[str | None] = mapped_column(String(32), nullable=True)


class BotRun(Base):
    __tablename__ = "bot_runs"

    id: Mapped[IntPk]
    started_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    stopped_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    environment: Mapped[str] = mapped_column(String(8), nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
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
    fees: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    funding: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    realized_pnl: Mapped[Decimal | None] = mapped_column(nullable=True)
    r_multiple: Mapped[Decimal | None] = mapped_column(nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
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
    trade_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("trades.id"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(nullable=True)
    qty: Mapped[Decimal]
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
    "Strategy",
    "Trade",
    "User",
    "WithdrawalMark",
]
