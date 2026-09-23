"""Monthly ledger API: per-calendar-month P&L, breakers, withdrawal allowance.

Withdrawal rule (BSD §19 future / prototype): 10% of positive realized net profit,
manual bookkeeping only — CryptoPilot never moves funds.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.db.session import get_session
from app.services import monthly_ledger as ledger

router = APIRouter(prefix="/api/monthly", tags=["monthly"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


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
    return [
        MonthRow(
            month=row.month,
            trades=row.trades,
            realized_pnl=str(row.realized_pnl),
            fees=str(row.fees),
            net=str(row.net),
            withdrawn=str(row.withdrawn),
            withdrawable=str(row.withdrawable),
            long_breaker="Healthy",
            short_breaker="Healthy",
        )
        for row in await ledger.ledger_months(session)
    ]


@router.post("/mark-withdrawn", response_model=MessageOut)
async def mark_withdrawn(
    body: MarkWithdrawnIn, current: CurrentUserDep, session: SessionDep
) -> MessageOut:
    """Record a manual withdrawal for a month (idempotent per month; no funds move)."""
    amount = await ledger.mark_withdrawn(session, month=body.month, by=current.user.email)
    if amount is None:
        return MessageOut(message="already marked")
    return MessageOut(message=f"marked {amount} withdrawn for {body.month}")
