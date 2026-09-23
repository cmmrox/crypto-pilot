"""Trades API: filterable history, per-trade detail with orders, CSV export."""

from __future__ import annotations

import csv
import io
import math
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.db.models import Trade
from app.db.session import get_session
from app.services.trade_history import (
    InvalidMonthError,
    TradeFilter,
    stream_trades,
    trade_outcome,
    trade_page,
    trade_with_orders,
    validate_filter,
)

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
        outcome=trade_outcome(t),
    )


def _selection(
    side: str | None,
    environment: str | None,
    strategy: str | None,
    month: str | None,
    search: str | None,
) -> TradeFilter:
    selection = TradeFilter(side, environment, strategy, month, search)
    try:
        validate_filter(selection)
    except InvalidMonthError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="month must be a valid YYYY-MM value",
        ) from exc
    return selection


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
    selection = _selection(side, environment, strategy, month, search)
    total, rows = await trade_page(session, selection, page=page, page_size=page_size)
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
    selection = _selection(side, environment, strategy, month, search)

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
        async for trade in stream_trades(session, selection):
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
    found = await trade_with_orders(session, trade_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="trade not found")
    t, orders = found
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
