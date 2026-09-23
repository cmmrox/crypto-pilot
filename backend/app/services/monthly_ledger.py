"""Monthly ledger: realized results per UTC month and the manual withdrawal allowance."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.db.models import Trade, WithdrawalMark

# The owner may withdraw 10% of a month's positive net result (BSD monthly ledger).
WITHDRAWAL_RATE = Decimal("0.10")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class LedgerMonth:
    month: str
    trades: int
    realized_pnl: Decimal
    fees: Decimal
    withdrawn: Decimal

    @property
    def net(self) -> Decimal:
        return self.realized_pnl - self.fees

    @property
    def withdrawable(self) -> Decimal:
        """Nothing once a withdrawal is marked; otherwise the allowance on a gain."""
        if self.withdrawn != 0:
            return Decimal("0").quantize(CENT)
        return withdrawal_allowance(self.net)


def withdrawal_allowance(net: Decimal) -> Decimal:
    return (max(Decimal("0"), net) * WITHDRAWAL_RATE).quantize(CENT)


def utc_month(column: InstrumentedAttribute[dt.datetime]) -> ColumnElement[str]:
    """The UTC calendar month (YYYY-MM) of a timestamptz column.

    Postgres renders timestamptz in the session's time zone, and production shares
    its database server with other applications, so the server default is not ours
    to rely on. The monthly breakers already use UTC months.
    """
    return func.to_char(func.timezone("UTC", column), "YYYY-MM")


async def ledger_months(session: AsyncSession) -> list[LedgerMonth]:
    """Closed trades grouped by the UTC month they opened in, newest month first."""
    month_col = utc_month(Trade.opened_at)
    rows = (
        await session.execute(
            select(
                month_col.label("m"),
                func.count(Trade.id),
                func.coalesce(func.sum(Trade.realized_pnl), 0),
                func.coalesce(func.sum(Trade.fees), 0),
            )
            .where(Trade.closed_at.is_not(None))
            .group_by(month_col)
            .order_by(month_col.desc())
        )
    ).all()
    marks = {m.month: m.amount for m in (await session.execute(select(WithdrawalMark))).scalars()}
    return [
        LedgerMonth(
            month=month,
            trades=int(count),
            realized_pnl=Decimal(str(realized)),
            fees=Decimal(str(fees)),
            withdrawn=marks.get(month, Decimal("0")),
        )
        for month, count, realized, fees in rows
    ]


async def mark_withdrawn(session: AsyncSession, *, month: str, by: str) -> Decimal | None:
    """Record the month's allowance as withdrawn; None if it was already marked.

    Bookkeeping only: no funds move.
    """
    existing = (
        await session.execute(select(WithdrawalMark).where(WithdrawalMark.month == month))
    ).scalar_one_or_none()
    if existing is not None:
        return None
    realized, fees = (
        await session.execute(
            select(
                func.coalesce(func.sum(Trade.realized_pnl), 0),
                func.coalesce(func.sum(Trade.fees), 0),
            ).where(Trade.closed_at.is_not(None), utc_month(Trade.opened_at) == month)
        )
    ).one()
    amount = withdrawal_allowance(Decimal(str(realized)) - Decimal(str(fees)))
    session.add(
        WithdrawalMark(month=month, amount=amount, marked_at=dt.datetime.now(dt.UTC), marked_by=by)
    )
    return amount
