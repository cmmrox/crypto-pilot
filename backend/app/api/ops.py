"""Operations API: kill switch and a DEMO execution self-check.

The kill switch cancels all orders and flattens all positions on the active
environment. The self-check places a minimal real DEMO round-trip to prove the
execution path end-to-end (DEMO only — refused on LIVE).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.db.session import get_session
from app.execution.filters import clamp_qty
from app.execution.orders import new_client_order_id
from app.execution.reconcile import reconcile_position
from app.services import execution_service as exec_svc
from app.services.events import record_event

router = APIRouter(prefix="/api/ops", tags=["ops"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class KillResult(BaseModel):
    ok: bool
    cancelled_orders: int
    detail: str


class SelfCheckResult(BaseModel):
    ok: bool
    filled_qty: str
    entry_price: str
    reconciled: bool
    flattened: bool
    detail: str


@router.post("/kill", response_model=KillResult)
async def kill_switch(current: CurrentUserDep, session: SessionDep) -> KillResult:
    """Cancel all orders and flatten all positions on the active environment."""
    try:
        async with exec_svc.execution_context(session) as ctx:
            cancelled = await ctx.orders.kill(session)
        return KillResult(ok=True, cancelled_orders=cancelled, detail="flattened and stopped")
    except exec_svc.NotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/self-check-round-trip", response_model=SelfCheckResult)
async def self_check(current: CurrentUserDep, session: SessionDep) -> SelfCheckResult:
    """Place a minimal real DEMO round-trip (entry → verify → flatten). DEMO only."""
    try:
        async with exec_svc.execution_context(session) as ctx:
            if ctx.environment != "DEMO":
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="self-check is DEMO-only")
            symbol = ctx.market.symbol
            filters = await ctx.exchange.get_filters(symbol)
            price = (await ctx.exchange.get_position(symbol)).entry_price
            if price <= 0:
                # flat → use account mark via a tiny public kline fetch
                from app.execution.binance_client import BinanceClient

                async with BinanceClient(ctx.environment) as md:
                    price = Decimal(
                        str(
                            (
                                await md.get_klines(
                                    symbol,
                                    ctx.market.interval,
                                    limit=1,
                                )
                            )[0].close
                        )
                    )
            qty = clamp_qty((filters.min_notional * Decimal("1.2")) / price, filters)
            entry = await ctx.exchange.place_market(
                symbol, "BUY", qty, client_order_id=new_client_order_id("SELF")
            )
            pos = await ctx.exchange.get_position(symbol)
            rec = await reconcile_position(ctx.exchange, symbol, expected_qty=pos.qty)
            # Always flatten.
            flattened = False
            if pos.qty != 0:
                await ctx.exchange.place_market(
                    symbol,
                    "SELL",
                    abs(pos.qty),
                    client_order_id=new_client_order_id("SELFX"),
                    reduce_only=True,
                )
                flattened = abs((await ctx.exchange.get_position(symbol)).qty) <= filters.step_size
            await record_event(
                session,
                level="INFO",
                category="system",
                message="DEMO execution self-check round-trip completed",
                ref="self_check",
                payload={
                    "qty": str(qty),
                    "entry": str(entry.avg_price),
                    "reconciled": rec.matched,
                    "flattened": flattened,
                },
            )
            return SelfCheckResult(
                ok=True,
                filled_qty=str(entry.filled_qty),
                entry_price=str(entry.avg_price),
                reconciled=rec.matched,
                flattened=flattened,
                detail="round-trip ok",
            )
    except exec_svc.NotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
