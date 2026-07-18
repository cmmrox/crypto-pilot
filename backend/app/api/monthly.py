"""Monthly ledger API: per-calendar-month P&L, breakers, withdrawal allowance.

Withdrawal rule (BSD §19 future / prototype): 10% of positive realized net profit,
manual bookkeeping only — CryptoPilot never moves funds.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.db.models import Trade, WithdrawalMark
from app.db.session import get_session

router = APIRouter(prefix="/api/monthly", tags=["monthly"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

WITHDRAWAL_RATE = Decimal("0.10")


class MonthRow(BaseModel):
    month: str
    trades: int
    realized_pnl: str
    fees: str
    net: str
    withdrawn: str
    withdrawable: str
    long_breaker: str
    short_breaker: str


class MarkWithdrawnIn(BaseModel):
    month: str


class MessageOut(BaseModel):
    message: str


@router.get("", response_model=list[MonthRow])
async def monthly_ledger(_current: CurrentUserDep, session: SessionDep) -> list[MonthRow]:
    month_col = func.to_char(Trade.opened_at, "YYYY-MM")
    stmt = (
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
    rows = (await session.execute(stmt)).all()

    marks = {
        m.month: m.amount
        for m in (await session.execute(select(WithdrawalMark))).scalars().all()
    }

    out: list[MonthRow] = []
    for m, count, realized, fees in rows:
        realized_d = Decimal(str(realized))
        fees_d = Decimal(str(fees))
        net = realized_d - fees_d
        withdrawn = marks.get(m, Decimal("0"))
        withdrawable = (
            max(Decimal("0"), net) * WITHDRAWAL_RATE if withdrawn == 0 else Decimal("0")
        )
        out.append(
            MonthRow(
                month=m,
                trades=int(count),
                realized_pnl=str(realized_d),
                fees=str(fees_d),
                net=str(net),
                withdrawn=str(withdrawn),
                withdrawable=str(withdrawable.quantize(Decimal("0.01"))),
                long_breaker="Healthy",
                short_breaker="Healthy",
            )
        )
    return out


@router.post("/mark-withdrawn", response_model=MessageOut)
async def mark_withdrawn(
    body: MarkWithdrawnIn, current: CurrentUserDep, session: SessionDep
) -> MessageOut:
    """Record a manual withdrawal for a month (idempotent per month; no funds move)."""
    existing = (
        await session.execute(
            select(WithdrawalMark).where(WithdrawalMark.month == body.month)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return MessageOut(message="already marked")

    # Compute the allowance for that month.
    month_col = func.to_char(Trade.opened_at, "YYYY-MM")
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(Trade.realized_pnl), 0),
                func.coalesce(func.sum(Trade.fees), 0),
            ).where(Trade.closed_at.is_not(None), month_col == body.month)
        )
    ).one()
    net = Decimal(str(row[0])) - Decimal(str(row[1]))
    amount = (max(Decimal("0"), net) * WITHDRAWAL_RATE).quantize(Decimal("0.01"))
    session.add(
        WithdrawalMark(
            month=body.month,
            amount=amount,
            marked_at=dt.datetime.now(dt.UTC),
            marked_by=current.user.email,
        )
    )
    return MessageOut(message=f"marked {amount} withdrawn for {body.month}")
