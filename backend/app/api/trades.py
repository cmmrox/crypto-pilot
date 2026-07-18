"""Trades API: filterable history, per-trade detail with orders, CSV export."""

from __future__ import annotations

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.db.models import Order, Trade
from app.db.session import get_session

router = APIRouter(prefix="/api/trades", tags=["trades"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class TradeOut(BaseModel):
    id: int
    opened_at: str
    closed_at: str | None
    side: str
    entry_px: str
    exit_px: str | None
    qty: str
    fees: str
    realized_pnl: str | None
    r_multiple: str | None
    exit_reason: str | None
    strategy: str
    environment: str
    outcome: str


class OrderOut(BaseModel):
    client_order_id: str
    binance_order_id: str | None
    type: str
    status: str
    qty: str
    price: str | None
    stop_price: str | None
    reduce_only: bool


class TradeDetailOut(TradeOut):
    orders: list[OrderOut]


def _outcome(t: Trade) -> str:
    if t.closed_at is None:
        return "OPEN"
    if t.realized_pnl is None:
        return "OPEN"
    return "WIN" if t.realized_pnl > 0 else "LOSS"


def _to_out(t: Trade) -> TradeOut:
    return TradeOut(
        id=t.id,
        opened_at=t.opened_at.isoformat(),
        closed_at=t.closed_at.isoformat() if t.closed_at else None,
        side=t.side,
        entry_px=str(t.entry_px),
        exit_px=str(t.exit_px) if t.exit_px is not None else None,
        qty=str(t.qty),
        fees=str(t.fees),
        realized_pnl=str(t.realized_pnl) if t.realized_pnl is not None else None,
        r_multiple=str(t.r_multiple) if t.r_multiple is not None else None,
        exit_reason=t.exit_reason,
        strategy=t.strategy,
        environment=t.environment,
        outcome=_outcome(t),
    )


def _filtered_query(
    side: str | None,
    environment: str | None,
    strategy: str | None,
    month: str | None,
    search: str | None,
) -> Select[tuple[Trade]]:
    stmt = select(Trade).order_by(Trade.opened_at.desc())
    if side:
        stmt = stmt.where(Trade.side == side)
    if environment:
        stmt = stmt.where(Trade.environment == environment)
    if strategy:
        stmt = stmt.where(Trade.strategy == strategy)
    if month:
        from sqlalchemy import func

        stmt = stmt.where(func.to_char(Trade.opened_at, "YYYY-MM") == month)
    if search:
        from sqlalchemy import String, cast, func, or_

        like = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(func.coalesce(Trade.exit_reason, "")).like(like),
                cast(Trade.id, String).like(f"%{search}%"),
            )
        )
    return stmt


@router.get("", response_model=list[TradeOut])
async def list_trades(
    _current: CurrentUserDep,
    session: SessionDep,
    side: Annotated[str | None, Query()] = None,
    environment: Annotated[str | None, Query()] = None,
    strategy: Annotated[str | None, Query()] = None,
    month: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
) -> list[TradeOut]:
    stmt = _filtered_query(side, environment, strategy, month, search)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_out(t) for t in rows]


@router.get("/export.csv")
async def export_csv(
    _current: CurrentUserDep,
    session: SessionDep,
    side: Annotated[str | None, Query()] = None,
    environment: Annotated[str | None, Query()] = None,
    strategy: Annotated[str | None, Query()] = None,
    month: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
) -> StreamingResponse:
    rows = (
        await session.execute(_filtered_query(side, environment, strategy, month, search))
    ).scalars().all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        ["id", "opened_at", "closed_at", "side", "environment", "strategy",
         "entry_px", "exit_px", "qty", "fees", "realized_pnl", "r_multiple", "exit_reason"]
    )
    for t in rows:
        w.writerow(
            [t.id, t.opened_at.isoformat(), t.closed_at.isoformat() if t.closed_at else "",
             t.side, t.environment, t.strategy, t.entry_px, t.exit_px or "", t.qty, t.fees,
             t.realized_pnl if t.realized_pnl is not None else "",
             t.r_multiple if t.r_multiple is not None else "", t.exit_reason or ""]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cryptopilot-trades.csv"},
    )


@router.get("/{trade_id}", response_model=TradeDetailOut)
async def trade_detail(
    trade_id: int, _current: CurrentUserDep, session: SessionDep
) -> TradeDetailOut:
    t = (await session.execute(select(Trade).where(Trade.id == trade_id))).scalar_one_or_none()
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="trade not found")
    orders = (
        await session.execute(select(Order).where(Order.trade_id == trade_id).order_by(Order.id))
    ).scalars().all()
    base = _to_out(t)
    return TradeDetailOut(
        **base.model_dump(),
        orders=[
            OrderOut(
                client_order_id=o.client_order_id,
                binance_order_id=o.binance_order_id,
                type=o.type,
                status=o.status,
                qty=str(o.qty),
                price=str(o.price) if o.price is not None else None,
                stop_price=str(o.stop_price) if o.stop_price is not None else None,
                reduce_only=o.reduce_only,
            )
            for o in orders
        ],
    )
