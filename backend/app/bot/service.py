"""BotService: 24/7 lifecycle + the per-close decision that ties strategy → risk
→ execution together (BSD FR-02/FR-03).

Lifecycle: start (connect → reconcile → resume) / safe stop (leave position) /
stop & close (flatten then stop) / kill / safe mode. State survives restarts: the
latest open bot_run means "was running", so a restart resumes and reconciles.

The decision path (evaluate_once) is pure of scheduling so it is unit-testable with
a FakeExchange + seeded candles.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.state import BotSnapshot, BotStatus
from app.core.logging import get_logger
from app.db.models import BotRun, Candle, EquitySnapshot
from app.execution.exchange import Exchange
from app.execution.filters import SymbolFilters
from app.execution.orders import OrderManager
from app.execution.reconcile import reconcile_position
from app.risk.sizing import SizingResult, size_long
from app.services.events import record_event
from app.services.settings_store import get_settings_row
from app.strategies import EnterLong, EnterShort, ExitAll, TradeState, get_strategy
from app.strategies.base import Candle as StratCandle

_log = get_logger("bot")
SYMBOL = "BTCUSDT"
INTERVAL = "4h"


class BotService:
    """Owns bot lifecycle state and the decision path."""

    async def status(self, session: AsyncSession) -> BotSnapshot:
        run = await self._current_run(session)
        settings_row = await get_settings_row(session)
        if run is None:
            return BotSnapshot(
                BotStatus.STOPPED,
                settings_row.active_environment,
                settings_row.active_strategy,
                None,
                None,
                None,
            )
        status = BotStatus.SAFE_MODE if run.stop_reason == "safe_mode" else BotStatus.RUNNING
        return BotSnapshot(
            status,
            run.environment,
            run.strategy,
            run.id,
            run.started_at,
            None,
        )

    async def _current_run(self, session: AsyncSession) -> BotRun | None:
        """The open run (no stopped_at) means the bot is running/safe-mode."""
        return (
            await session.execute(
                select(BotRun)
                .where(BotRun.stopped_at.is_(None))
                .order_by(BotRun.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def start(self, session: AsyncSession, exchange: Exchange, *, by: str) -> BotRun:
        """Connect, reconcile, and begin running."""
        # Shared settings-row lock serializes bot start with environment,
        # strategy, and active-credential changes.
        settings_row = await get_settings_row(session, for_update=True)
        if await self._current_run(session) is not None:
            raise RuntimeError("bot already running")
        # Reconcile before acting (account is source of truth).
        expected = await self._expected_position(session)
        rec = await reconcile_position(exchange, SYMBOL, expected_qty=expected)
        run = BotRun(
            started_at=dt.datetime.now(dt.UTC),
            environment=settings_row.active_environment,
            strategy=settings_row.active_strategy,
            started_by=by,
            stop_reason="safe_mode" if not rec.matched else None,
        )
        session.add(run)
        await session.flush()
        await record_event(
            session,
            level="INFO" if rec.matched else "WARN",
            category="bot",
            message="Bot started" + ("" if rec.matched else " in SAFE MODE (reconcile mismatch)"),
            ref=f"bot_run:{run.id}",
            payload={
                "environment": run.environment,
                "strategy": run.strategy,
                "reconciled": rec.matched,
                "detail": rec.detail,
            },
        )
        from app.services.notify_config import notify_event

        await notify_event(
            session,
            kind="bot_started",
            payload={"environment": run.environment, "strategy": run.strategy, "equity": "—"},
        )
        return run

    async def stop(self, session: AsyncSession, *, reason: str = "user") -> None:
        """Safe stop: stop evaluating, leave the position as-is."""
        run = await self._current_run(session)
        if run is None:
            return
        run.stopped_at = dt.datetime.now(dt.UTC)
        run.stop_reason = reason
        await record_event(
            session,
            level="INFO",
            category="bot",
            message="Bot stopped — open position left with its exchange stops",
            ref=f"bot_run:{run.id}",
            payload={"reason": reason},
        )
        from app.services.notify_config import notify_event

        await notify_event(session, kind="bot_stopped", payload={"actor": reason})

    async def stop_and_close(
        self, session: AsyncSession, exchange: Exchange, orders: OrderManager
    ) -> None:
        """Flatten the position at market, then stop."""
        pos = await exchange.get_position(SYMBOL)
        if pos.qty != 0:
            side = "LONG" if pos.qty > 0 else "SHORT"
            await orders.flatten(session, side=side, qty=pos.qty, reason="stop & close")
        await self.stop(session, reason="user")

    async def kill(self, session: AsyncSession, orders: OrderManager) -> int:
        """Kill switch: cancel all, flatten, stop."""
        cancelled = await orders.kill(session)
        run = await self._current_run(session)
        if run is not None:
            run.stopped_at = dt.datetime.now(dt.UTC)
            run.stop_reason = "kill"
        return cancelled

    async def enter_safe_mode(self, session: AsyncSession, *, reason: str) -> None:
        run = await self._current_run(session)
        if run is not None:
            run.stop_reason = "safe_mode"
            await record_event(
                session,
                level="WARN",
                category="bot",
                message=f"Safe mode: {reason}",
                ref=f"bot_run:{run.id}",
                payload={"reason": reason},
            )

    async def _expected_position(self, session: AsyncSession) -> Decimal:
        """Signed qty the bot believes it holds (from open trades)."""
        from app.db.models import Trade

        rows = (
            (await session.execute(select(Trade).where(Trade.closed_at.is_(None)))).scalars().all()
        )
        total = Decimal("0")
        for t in rows:
            total += t.qty if t.side == "LONG" else -t.qty
        return total

    async def write_equity_snapshot(self, session: AsyncSession, exchange: Exchange) -> None:
        """Record an equity snapshot (every 4h close — FR-12)."""
        acct = await exchange.get_account()
        settings_row = await get_settings_row(session)
        session.add(
            EquitySnapshot(
                ts=dt.datetime.now(dt.UTC),
                environment=settings_row.active_environment,
                balance=acct.balance,
                unrealized_pnl=acct.unrealized_pnl,
            )
        )

    async def evaluate_once(
        self,
        session: AsyncSession,
        exchange: Exchange,
        orders: OrderManager,
        *,
        candles: list[Candle],
    ) -> list[str]:
        """One closed-candle decision: reconcile → strategy → risk → execute.

        Returns a list of action strings taken (for logging/testing). Only runs
        when the bot is RUNNING (not safe mode / stopped).
        """
        run = await self._current_run(session)
        if run is None or run.stop_reason == "safe_mode":
            return []

        expected = await self._expected_position(session)
        reconciliation = await reconcile_position(exchange, SYMBOL, expected_qty=expected)
        if not reconciliation.matched:
            await self.enter_safe_mode(
                session, reason=f"every-close reconciliation: {reconciliation.detail}"
            )
            await record_event(
                session,
                level="WARN",
                category="reconciliation",
                message="Closed-candle decision blocked by reconciliation mismatch",
                ref=f"bot_run:{run.id}",
                payload={
                    "expected_qty": str(reconciliation.expected_qty),
                    "actual_qty": str(reconciliation.actual_qty),
                },
            )
            return ["safe_mode"]

        acct = await exchange.get_account()
        equity = acct.balance
        pos = await exchange.get_position(SYMBOL)
        filters = await exchange.get_filters(SYMBOL)
        settings_row = await get_settings_row(session)

        strat = get_strategy(settings_row.active_strategy)
        strat_candles = [
            StratCandle(
                open_time_ms=int(c.open_time.timestamp() * 1000),
                open=float(c.open),
                high=float(c.high),
                low=float(c.low),
                close=float(c.close),
                volume=float(c.volume),
            )
            for c in candles
        ]
        short_weight = 0.0
        if pos.qty < 0 and equity > 0:
            short_weight = float(abs(pos.qty) * pos.entry_price / equity)
        state = TradeState(
            equity=float(equity),
            long_position=pos.qty > 0,
            short_weight=short_weight,
        )
        intents = strat.on_candle(strat_candles, state)
        actions: list[str] = []
        last_close = Decimal(str(candles[-1].close))

        for intent in intents:
            if isinstance(intent, EnterLong) and pos.qty == 0:
                sizing = size_long(
                    equity=equity,
                    risk_pct=settings_row.risk_pct,
                    stop_distance=Decimal(str(intent.stop_distance)),
                    price=last_close,
                    leverage_cap=settings_row.leverage_cap,
                    filters=filters,
                )
                if sizing.ok:
                    stop_price = last_close - Decimal(str(intent.stop_distance))
                    tp_r, tp_frac = intent.tp_levels[0]
                    tp1_price = last_close + Decimal(str(tp_r)) * Decimal(str(intent.stop_distance))
                    await orders.open_long(
                        session,
                        sizing=sizing,
                        stop_price=stop_price,
                        tp1_price=tp1_price,
                        tp1_fraction=Decimal(str(tp_frac)),
                        strategy=strat.name,
                        bot_run_id=run.id,
                    )
                    actions.append("open_long")
            elif isinstance(intent, EnterShort) and pos.qty == 0:
                sizing = _size_short_from_intent(intent, equity, last_close, settings_row, filters)
                if sizing.ok:
                    await orders.open_short(
                        session, sizing=sizing, strategy=strat.name, bot_run_id=run.id
                    )
                    actions.append("open_short")
            elif isinstance(intent, ExitAll) and pos.qty != 0:
                side = "LONG" if pos.qty > 0 else "SHORT"
                await orders.flatten(session, side=side, qty=pos.qty, reason=intent.reason)
                actions.append("exit_all")

        await self.write_equity_snapshot(session, exchange)
        return actions


def _size_short_from_intent(
    intent: EnterShort,
    equity: Decimal,
    price: Decimal,
    settings_row: object,
    filters: SymbolFilters,
) -> SizingResult:
    """Size the short from the strategy's already-vol-scaled weight."""
    from app.execution.filters import clamp_qty, meets_min_notional
    from app.risk.sizing import SizingResult

    weight = Decimal(str(intent.weight))
    notional = equity * weight
    qty = clamp_qty(notional / price, filters)
    if qty <= 0 or not meets_min_notional(qty, price, filters):
        return SizingResult(Decimal("0"), Decimal("0"), Decimal("0"), False, "below min")
    return SizingResult(qty, qty * price, (qty * price) / equity, True, "ok")


bot_service = BotService()
