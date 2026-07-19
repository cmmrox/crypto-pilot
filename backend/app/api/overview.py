"""Overview API: the real-time dashboard aggregate (BSD §12 Overview).

Account truth comes from Binance; equity curve + breakers from persisted snapshots
and trades. Polled by the dashboard for near-real-time updates.
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
from app.bot.service import bot_service
from app.db.models import EquitySnapshot, Trade
from app.db.session import get_session
from app.execution.binance_client import BinanceError
from app.risk.breakers import evaluate_breaker
from app.services import execution_service as exec_svc
from app.services.settings_store import get_settings_row

router = APIRouter(prefix="/api/overview", tags=["overview"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SYMBOL = "BTCUSDT"


class PositionOut(BaseModel):
    side: str | None
    qty: str
    entry_price: str
    mark_price: str
    unrealized_pnl: str
    leverage: str
    has_price_stop: bool


class BreakerOut(BaseModel):
    book: str
    month_to_date_pnl: str
    drawdown_pct: str
    tripped: bool


class OverviewOut(BaseModel):
    environment: str
    bot_status: str
    strategy: str
    exchange_reachable: bool
    balance: str
    equity: str
    unrealized_pnl: str
    position: PositionOut | None
    breakers: list[BreakerOut]
    month_realized_pnl: str


def _month_bounds(now: dt.datetime) -> dt.datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@router.get("", response_model=OverviewOut)
async def overview(current: CurrentUserDep, session: SessionDep) -> OverviewOut:
    settings_row = await get_settings_row(session)
    snap = await bot_service.status(session)

    balance = Decimal("0")
    equity = Decimal("0")
    upnl = Decimal("0")
    reachable = False
    position: PositionOut | None = None

    try:
        async with exec_svc.execution_context(session) as ctx:
            acct = await ctx.exchange.get_account()
            reachable = True
            balance = acct.balance
            upnl = acct.unrealized_pnl
            equity = balance + upnl
            pos = await ctx.exchange.get_position(SYMBOL)
            if pos.qty != 0:
                side = "LONG" if pos.qty > 0 else "SHORT"
                lev = abs(pos.qty) * pos.entry_price / balance if balance > 0 else Decimal("0")
                position = PositionOut(
                    side=side,
                    qty=str(abs(pos.qty)),
                    entry_price=str(pos.entry_price),
                    mark_price=str(pos.entry_price),
                    unrealized_pnl=str(upnl),
                    leverage=f"{lev:.2f}",
                    has_price_stop=(side == "LONG"),
                )
    except (exec_svc.NotConfiguredError, BinanceError):
        reachable = False

    # Month-to-date realized P&L per book (from closed trades).
    month_start = _month_bounds(dt.datetime.now(dt.UTC))
    breakers = []
    month_realized = Decimal("0")
    for book, sides in (("Long book", ("LONG",)), ("Short sleeve", ("SHORT",))):
        stmt = select(func.coalesce(func.sum(Trade.realized_pnl), 0)).where(
            Trade.closed_at >= month_start, Trade.side.in_(sides)
        )
        pnl = Decimal(str((await session.execute(stmt)).scalar_one()))
        month_realized += pnl
        st = evaluate_breaker(month_start_equity=equity or Decimal("1"), month_to_date_pnl=pnl)
        breakers.append(
            BreakerOut(
                book=book, month_to_date_pnl=str(pnl),
                drawdown_pct=f"{st.drawdown_pct:.4f}", tripped=st.tripped,
            )
        )

    return OverviewOut(
        environment=settings_row.active_environment,
        bot_status=snap.status.value,
        strategy=settings_row.active_strategy,
        exchange_reachable=reachable,
        balance=str(balance),
        equity=str(equity),
        unrealized_pnl=str(upnl),
        position=position,
        breakers=breakers,
        month_realized_pnl=str(month_realized),
    )


class EquityPoint(BaseModel):
    ts: str
    equity: str


@router.get("/equity", response_model=list[EquityPoint])
async def equity_curve(
    current: CurrentUserDep, session: SessionDep, limit: int = 500
) -> list[EquityPoint]:
    settings_row = await get_settings_row(session)
    rows = (
        (
            await session.execute(
                select(EquitySnapshot)
                .where(EquitySnapshot.environment == settings_row.active_environment)
                .order_by(EquitySnapshot.ts.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    rows = list(reversed(rows))
    return [
        EquityPoint(ts=r.ts.isoformat(), equity=str(r.balance + r.unrealized_pnl)) for r in rows
    ]
