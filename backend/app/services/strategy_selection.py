"""Guarded selection of the canonical active strategy."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.service import bot_service
from app.bot.state import BotStatus
from app.db.models import Trade
from app.services.events import record_event
from app.services.settings_store import get_settings_row
from app.strategies import get_strategy


class StrategySelectionBlockedError(RuntimeError):
    """The runtime is not in a safe state for changing strategy."""


class UnknownStrategyError(ValueError):
    """The requested strategy is not registered."""


async def select_active_strategy(
    session: AsyncSession,
    *,
    requested_name: str,
    actor_email: str,
) -> str:
    """Select a canonical strategy while the bot is stopped and locally flat."""
    row = await get_settings_row(session, for_update=True)
    snapshot = await bot_service.status(session)
    if snapshot.status != BotStatus.STOPPED:
        raise StrategySelectionBlockedError("Stop the bot before changing strategy.")

    open_trade_id = (
        await session.execute(select(Trade.id).where(Trade.closed_at.is_(None)).limit(1))
    ).scalar_one_or_none()
    if open_trade_id is not None:
        raise StrategySelectionBlockedError("Close the active position before changing strategy.")

    try:
        strategy = get_strategy(requested_name)
    except KeyError as exc:
        raise UnknownStrategyError("unknown strategy") from exc

    manifest = strategy.manifest
    selected = manifest.strategy_id
    previous = row.active_strategy
    row.active_strategy = selected
    await record_event(
        session,
        level="INFO",
        category="strategy",
        message=f"Active strategy switched {previous} → {selected}",
        ref="strategy_switch",
        payload={
            "from": previous,
            "to": selected,
            "by": actor_email,
            "release": manifest.release,
            "symbol": manifest.market.symbol,
            "interval": manifest.market.interval,
            "parameters": dict(strategy.params),
        },
    )
    await session.commit()
    return selected
