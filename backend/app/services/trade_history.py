"""Trade history queries for the owner console (Trades view, CSV export, detail)."""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy import ColumnElement, Select, String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Order, Trade


class InvalidMonthError(ValueError):
    """A month filter that is not a real calendar month."""


@dataclass(frozen=True)
class TradeFilter:
    side: str | None = None
    environment: str | None = None
    strategy: str | None = None
    month: str | None = None  # YYYY-MM, by opening time in UTC
    search: str | None = None  # exit reason text or trade id


def trade_outcome(trade: Trade) -> str:
    """OPEN until realized; otherwise WIN for a positive P&L, else LOSS."""
    if trade.closed_at is None or trade.realized_pnl is None:
        return "OPEN"
    return "WIN" if trade.realized_pnl > 0 else "LOSS"


async def trade_page(
    session: AsyncSession, selection: TradeFilter, *, page: int, page_size: int
) -> tuple[int, list[Trade]]:
    """Return the total matching count and one page of trades, newest first."""
    conditions = _conditions(selection)
    total = (await session.execute(select(func.count(Trade.id)).where(*conditions))).scalar_one()
    rows = (
        (
            await session.execute(
                _ordered(conditions).offset((page - 1) * page_size).limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return total, list(rows)


async def stream_trades(session: AsyncSession, selection: TradeFilter) -> AsyncIterator[Trade]:
    """Stream every matching trade, newest first, without loading them all."""
    result = await session.stream_scalars(_ordered(_conditions(selection)))
    async for trade in result:
        yield trade


async def trade_with_orders(
    session: AsyncSession, trade_id: int
) -> tuple[Trade, list[Order]] | None:
    trade = (await session.execute(select(Trade).where(Trade.id == trade_id))).scalar_one_or_none()
    if trade is None:
        return None
    orders = (
        (await session.execute(select(Order).where(Order.trade_id == trade_id).order_by(Order.id)))
        .scalars()
        .all()
    )
    return trade, list(orders)


def validate_filter(selection: TradeFilter) -> None:
    """Raise InvalidMonthError before any work starts (e.g. a streamed export)."""
    _conditions(selection)


def _conditions(selection: TradeFilter) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if selection.side:
        conditions.append(Trade.side == selection.side)
    if selection.environment:
        conditions.append(Trade.environment == selection.environment)
    if selection.strategy:
        conditions.append(Trade.strategy == selection.strategy)
    if selection.month:
        start, end = _utc_month_bounds(selection.month)
        conditions.extend((Trade.opened_at >= start, Trade.opened_at < end))
    if selection.search:
        like = f"%{selection.search.lower()}%"
        conditions.append(
            or_(
                func.lower(func.coalesce(Trade.exit_reason, "")).like(like),
                cast(Trade.id, String).like(f"%{selection.search}%"),
            )
        )
    return conditions


def _utc_month_bounds(month: str) -> tuple[dt.datetime, dt.datetime]:
    try:
        month_start = dt.date.fromisoformat(f"{month}-01")
    except ValueError as exc:
        raise InvalidMonthError(month) from exc
    next_month = (
        dt.date(month_start.year + 1, 1, 1)
        if month_start.month == 12
        else dt.date(month_start.year, month_start.month + 1, 1)
    )
    return (
        dt.datetime.combine(month_start, dt.time.min, tzinfo=dt.UTC),
        dt.datetime.combine(next_month, dt.time.min, tzinfo=dt.UTC),
    )


def _ordered(conditions: list[ColumnElement[bool]]) -> Select[tuple[Trade]]:
    return select(Trade).where(*conditions).order_by(Trade.opened_at.desc(), Trade.id.desc())
