"""Trades API: filterable history, per-trade detail with orders, CSV export."""

from __future__ import annotations

import csv
import datetime as dt
import io
import math
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

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


class TradePageOut(BaseModel):
    items: list[TradeOut]
    total: int
    page: int
    page_size: int
    total_pages: int


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


def _trade_filters(
    side: Literal["LONG", "SHORT"] | None,
    environment: Literal["DEMO", "LIVE"] | None,
    strategy: str | None,
    month: str | None,
    search: str | None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    if side:
        filters.append(Trade.side == side)
    if environment:
        filters.append(Trade.environment == environment)
    if strategy:
        filters.append(Trade.strategy == strategy)
    if month:
        try:
            month_start = dt.date.fromisoformat(f"{month}-01")
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="month must be a valid YYYY-MM value",
            ) from exc
        next_month = (
            dt.date(month_start.year + 1, 1, 1)
            if month_start.month == 12
            else dt.date(month_start.year, month_start.month + 1, 1)
        )
        start = dt.datetime.combine(month_start, dt.time.min, tzinfo=dt.UTC)
        end = dt.datetime.combine(next_month, dt.time.min, tzinfo=dt.UTC)
        filters.extend((Trade.opened_at >= start, Trade.opened_at < end))
    if search:
        from sqlalchemy import String, cast

        like = f"%{search.lower()}%"
        filters.append(
            or_(
                func.lower(func.coalesce(Trade.exit_reason, "")).like(like),
                cast(Trade.id, String).like(f"%{search}%"),
            )
        )
    return filters


def _filtered_query(filters: list[ColumnElement[bool]]) -> Select[tuple[Trade]]:
    return select(Trade).where(*filters).order_by(Trade.opened_at.desc(), Trade.id.desc())


@router.get("", response_model=TradePageOut)
async def list_trades(
    _current: CurrentUserDep,
    session: SessionDep,
    side: Annotated[Literal["LONG", "SHORT"] | None, Query()] = None,
    environment: Annotated[Literal["DEMO", "LIVE"] | None, Query()] = None,
    strategy: Annotated[str | None, Query(max_length=64)] = None,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 50,
) -> TradePageOut:
    filters = _trade_filters(side, environment, strategy, month, search)
    total = (await session.execute(select(func.count(Trade.id)).where(*filters))).scalar_one()
    stmt = _filtered_query(filters).offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(stmt)).scalars().all()
    return TradePageOut(
        items=[_to_out(t) for t in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size),
    )


@router.get("/export.csv")
async def export_csv(
    _current: CurrentUserDep,
    session: SessionDep,
    side: Annotated[Literal["LONG", "SHORT"] | None, Query()] = None,
    environment: Annotated[Literal["DEMO", "LIVE"] | None, Query()] = None,
    strategy: Annotated[str | None, Query(max_length=64)] = None,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> StreamingResponse:
    filters = _trade_filters(side, environment, strategy, month, search)

    async def generate() -> AsyncIterator[str]:
        buf = io.StringIO()
        writer = csv.writer(buf)

        def line(values: list[object]) -> str:
            buf.seek(0)
            buf.truncate(0)
            writer.writerow(values)
            return buf.getvalue()

        yield line(
            [
                "id",
                "opened_at",
                "closed_at",
                "side",
                "environment",
                "strategy",
                "entry_px",
                "exit_px",
                "qty",
                "fees",
                "realized_pnl",
                "r_multiple",
                "exit_reason",
            ]
        )
        result = await session.stream_scalars(_filtered_query(filters))
        async for trade in result:
            yield line(
                [
                    trade.id,
                    trade.opened_at.isoformat(),
                    trade.closed_at.isoformat() if trade.closed_at else "",
                    trade.side,
                    trade.environment,
                    trade.strategy,
                    trade.entry_px,
                    trade.exit_px or "",
                    trade.qty,
                    trade.fees,
                    trade.realized_pnl if trade.realized_pnl is not None else "",
                    trade.r_multiple if trade.r_multiple is not None else "",
                    trade.exit_reason or "",
                ]
            )

    return StreamingResponse(
        generate(),
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
        (await session.execute(select(Order).where(Order.trade_id == trade_id).order_by(Order.id)))
        .scalars()
        .all()
    )
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
