"""Owner SMS for trade lifecycle events, shared by every execution path.

A trade can close because the bot flattened it (manual close, regime exit, breaker,
kill switch) or because Binance filled a resting stop/target. Both paths must send
the same "trade closed" alert (BSD FR-06), so the payload is built here once.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Trade

ZERO = Decimal("0")


def net_pnl(trade: Trade) -> Decimal:
    """Realized P&L after fees, plus funding received (negative when paid)."""
    return (trade.realized_pnl or ZERO) - (trade.fees or ZERO) + (trade.funding or ZERO)


def format_usdt(value: Decimal) -> str:
    return f"{value:+.2f} USDT"


def plain(value: Decimal | None, missing: str = "—") -> str:
    """Price/quantity without numeric(20,8) padding: 60000.00000000 -> 60000."""
    if value is None:
        return missing
    text = format(value.normalize(), "f")
    return "0" if text in {"-0", ""} else text


async def month_closed_net_pnl(session: AsyncSession, trade: Trade) -> Decimal:
    """Net P&L of this environment's trades closed this UTC month, including `trade`."""
    closed_at = trade.closed_at or dt.datetime.now(dt.UTC)
    month_start = closed_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    others = (
        (
            await session.execute(
                select(Trade).where(
                    Trade.environment == trade.environment,
                    Trade.closed_at.is_not(None),
                    Trade.closed_at >= month_start,
                    Trade.id != trade.id,
                )
            )
        )
        .scalars()
        .all()
    )
    return net_pnl(trade) + sum((net_pnl(other) for other in others), ZERO)


async def notify_trade_closed(session: AsyncSession, trade: Trade, *, reason: str) -> None:
    """Send the owner the closed-trade SMS once the trade row carries its exit."""
    from app.services.notify_config import notify_event

    await notify_event(
        session,
        kind="trade_closed",
        payload={
            "side": trade.side,
            "exit": plain(trade.exit_px),
            "reason": reason,
            "pnl": format_usdt(net_pnl(trade)),
            "month_pnl": format_usdt(await month_closed_net_pnl(session, trade)),
            "environment": trade.environment,
        },
    )


async def notify_tp1_filled(
    session: AsyncSession,
    trade: Trade,
    *,
    qty: Decimal,
    price: Decimal | None,
    remaining: Decimal,
    stop: Decimal | None,
) -> None:
    """Send the owner the first-target SMS after a partial take-profit fill."""
    from app.services.notify_config import notify_event

    await notify_event(
        session,
        kind="tp1_filled",
        payload={
            "side": trade.side,
            "qty": plain(qty),
            "price": plain(price),
            "remaining": plain(remaining),
            "stop": plain(stop, missing="unconfirmed"),
            "environment": trade.environment,
        },
    )
