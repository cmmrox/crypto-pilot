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
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.scheduler import INTERVAL_SECONDS
from app.bot.state import BotSnapshot, BotStatus
from app.core.logging import get_logger
from app.db.models import BotRun, Candle, EquitySnapshot, Event, Trade
from app.execution.exchange import Exchange
from app.execution.filters import SymbolFilters, clamp_qty, meets_min_notional, round_price
from app.execution.orders import OrderManager
from app.execution.reconcile import reconcile_position
from app.execution.trade_sync import sync_open_trade
from app.risk.breakers import evaluate_breaker
from app.risk.sizing import SizingResult, margin_capped_qty, size_long
from app.services.events import record_event
from app.services.settings_store import get_settings_row
from app.strategies import (
    EnterLong,
    EnterShort,
    ExitAll,
    Halt,
    MoveStop,
    ResizeShort,
    TakePartial,
    TradeState,
    canonical_strategy_id,
    get_strategy,
)
from app.strategies.base import Candle as StratCandle

_log = get_logger("bot")


@dataclass(frozen=True)
class MonthlyRiskState:
    month: str
    month_start_equity: Decimal
    long_pnl: Decimal
    short_pnl: Decimal
    halted_long: bool
    halted_short: bool


class BotService:
    """Owns bot lifecycle state and the decision path."""

    async def status(self, session: AsyncSession) -> BotSnapshot:
        run = await self._current_run(session)
        settings_row = await get_settings_row(session)
        strategy_id = canonical_strategy_id(settings_row.active_strategy)
        if run is None:
            return BotSnapshot(
                BotStatus.STOPPED,
                settings_row.active_environment,
                strategy_id,
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
        strategy = get_strategy(settings_row.active_strategy)
        market = strategy.manifest.market
        # Reconcile before acting (account is source of truth).
        expected = await self._expected_position(session)
        rec = await reconcile_position(exchange, market.symbol, expected_qty=expected)
        latest_closed_candle = await session.scalar(
            select(Candle.open_time)
            .where(
                Candle.symbol == market.symbol,
                Candle.interval == market.interval,
                Candle.closed.is_(True),
            )
            .order_by(Candle.open_time.desc())
            .limit(1)
        )
        run = BotRun(
            started_at=dt.datetime.now(dt.UTC),
            environment=settings_row.active_environment,
            strategy=strategy.manifest.strategy_id,
            strategy_release=strategy.manifest.release,
            strategy_interval=market.interval,
            # A manual start never chases a signal whose validated next-open
            # execution point has already passed. The next newly closed candle is
            # the first one this run may evaluate.
            last_evaluated_candle_at=latest_closed_candle,
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
                "decision_baseline": (
                    latest_closed_candle.isoformat() if latest_closed_candle is not None else None
                ),
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
        run = await self._current_run(session)
        strategy_name = (
            run.strategy if run is not None else (await get_settings_row(session)).active_strategy
        )
        symbol = get_strategy(strategy_name).manifest.market.symbol
        pos = await exchange.get_position(symbol)
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
        from app.services.notify_config import notify_event

        await notify_event(
            session,
            kind="kill_switch",
            payload={"cancelled_orders": cancelled},
        )
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
            total += t.remaining_qty if t.side == "LONG" else -t.remaining_qty
        return total

    async def write_equity_snapshot(
        self,
        session: AsyncSession,
        exchange: Exchange,
        *,
        snapshot_at: dt.datetime,
        long_month_pnl: Decimal,
        short_month_pnl: Decimal,
    ) -> None:
        """Record an equity snapshot (every 4h close — FR-12)."""
        acct = await exchange.get_account()
        settings_row = await get_settings_row(session)
        existing = (
            await session.execute(
                select(EquitySnapshot).where(
                    EquitySnapshot.environment == settings_row.active_environment,
                    EquitySnapshot.ts == snapshot_at,
                )
            )
        ).scalar_one_or_none()
        row = existing or EquitySnapshot(
            ts=snapshot_at,
            environment=settings_row.active_environment,
            balance=acct.balance,
            unrealized_pnl=acct.unrealized_pnl,
        )
        row.balance = acct.balance
        row.unrealized_pnl = acct.unrealized_pnl
        row.month_to_date_pnl = long_month_pnl
        row.sleeve_month_pnl = short_month_pnl
        if existing is None:
            session.add(row)

    async def evaluate_once(
        self,
        session: AsyncSession,
        exchange: Exchange,
        orders: OrderManager,
        *,
        candles: list[Candle],
        allow_new_entries: bool = True,
    ) -> list[str]:
        """Synchronize fills, reconcile, enforce breakers, then manage/execute."""
        run = await self._current_run(session)
        if run is None or not candles:
            return []
        settings_row = await get_settings_row(session)
        strategy = get_strategy(run.strategy)
        market = strategy.manifest.market
        risk = strategy.manifest.risk
        decision_candle_at = candles[-1].open_time
        synced = await sync_open_trade(
            session,
            exchange,
            environment=settings_row.active_environment,
            symbol=market.symbol,
        )
        if not synced.matched:
            reconciliation = await reconcile_position(
                exchange, market.symbol, expected_qty=synced.expected_qty
            )
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
            run.last_evaluated_candle_at = decision_candle_at
            return ["safe_mode"]

        previous_decision = run.last_evaluated_candle_at
        if previous_decision is not None and decision_candle_at <= previous_decision:
            return []

        interval = dt.timedelta(seconds=INTERVAL_SECONDS[market.interval])
        missed_decision = (
            previous_decision is not None and decision_candle_at > previous_decision + interval
        )
        if missed_decision:
            assert previous_decision is not None
            allow_new_entries = False
            await self.enter_safe_mode(
                session,
                reason=(
                    "one or more closed-candle decisions were missed; "
                    "stale entries are blocked pending owner review"
                ),
            )
            await record_event(
                session,
                level="ERROR",
                category="reconciliation",
                message="Missed closed-candle decision; stale entries blocked",
                ref=f"bot_run:{run.id}",
                payload={
                    "previous_candle": previous_decision.isoformat(),
                    "current_candle": decision_candle_at.isoformat(),
                    "strategy": run.strategy,
                    "interval": market.interval,
                },
            )
            from app.services.notify_config import notify_event

            await notify_event(
                session,
                kind="error",
                payload={
                    "error": (
                        "missed closed-candle decision; stale entries blocked "
                        "and bot entered safe mode"
                    )
                },
            )

        acct = await exchange.get_account()
        equity = acct.balance + acct.unrealized_pnl
        pos = synced.position
        filters = await exchange.get_filters(market.symbol)
        execution_price = await exchange.get_mark_price(market.symbol)
        snapshot_at = candles[-1].open_time + dt.timedelta(
            seconds=INTERVAL_SECONDS[market.interval]
        )
        monthly = await self._monthly_risk_state(
            session,
            environment=settings_row.active_environment,
            snapshot_at=snapshot_at,
            equity=equity,
            active_trade=synced.trade,
        )
        actions: list[str] = []
        long_trip = evaluate_breaker(
            month_start_equity=monthly.month_start_equity,
            month_to_date_pnl=monthly.long_pnl,
            cap=risk.long_monthly_loss_cap,
        ).tripped
        short_trip = evaluate_breaker(
            month_start_equity=monthly.month_start_equity,
            month_to_date_pnl=monthly.short_pnl,
            cap=risk.short_monthly_loss_cap,
        ).tripped
        breaker_acted = False
        if long_trip and not monthly.halted_long:
            await self._trip_breaker(
                session,
                run=run,
                book="LONG",
                month=monthly.month,
                pnl=monthly.long_pnl,
                month_start_equity=monthly.month_start_equity,
            )
            actions.append("halt_long")
            if pos.qty > 0:
                await orders.flatten(
                    session,
                    side="LONG",
                    qty=pos.qty,
                    reason="long monthly breaker",
                )
                actions.append("breaker_exit_long")
                breaker_acted = True
        if short_trip and not monthly.halted_short:
            await self._trip_breaker(
                session,
                run=run,
                book="SHORT",
                month=monthly.month,
                pnl=monthly.short_pnl,
                month_start_equity=monthly.month_start_equity,
            )
            actions.append("halt_short")
            if pos.qty < 0:
                await orders.flatten(
                    session,
                    side="SHORT",
                    qty=pos.qty,
                    reason="short monthly breaker",
                )
                actions.append("breaker_exit_short")
                breaker_acted = True
        if breaker_acted:
            await self.write_equity_snapshot(
                session,
                exchange,
                snapshot_at=snapshot_at,
                long_month_pnl=monthly.long_pnl,
                short_month_pnl=monthly.short_pnl,
            )
            run.last_evaluated_candle_at = decision_candle_at
            return actions

        strat = strategy
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
        trade = synced.trade
        if trade is not None and trade.side == "LONG" and pos.qty > 0:
            candle_high = candles[-1].high
            trade.highest_high = max(
                trade.highest_high or trade.entry_px,
                candle_high,
            )
        last_long_closed_at = await session.scalar(
            select(Trade.closed_at)
            .where(
                Trade.environment == run.environment,
                Trade.side == "LONG",
                Trade.closed_at.is_not(None),
            )
            .order_by(Trade.closed_at.desc())
            .limit(1)
        )
        state = TradeState(
            equity=float(equity),
            long_position=pos.qty > 0,
            short_weight=short_weight,
            long_entry=(
                float(trade.entry_px) if trade is not None and trade.side == "LONG" else None
            ),
            long_stop=(float(synced.long_stop) if synced.long_stop is not None else None),
            highest_high=(
                float(trade.highest_high)
                if trade is not None and trade.highest_high is not None
                else None
            ),
            tp1_done=synced.tp1_done,
            last_long_closed_at_ms=(
                int(last_long_closed_at.timestamp() * 1000)
                if last_long_closed_at is not None
                else None
            ),
            halted_long=monthly.halted_long or long_trip,
            halted_short=monthly.halted_short or short_trip,
        )
        intents = strat.on_candle(strat_candles, state)
        entries_allowed = run.stop_reason != "safe_mode" and allow_new_entries

        for intent in intents:
            if (
                isinstance(intent, EnterLong)
                and pos.qty == 0
                and entries_allowed
                and not state.halted_long
            ):
                sizing = size_long(
                    equity=equity,
                    risk_pct=risk.long_risk_pct,
                    stop_distance=Decimal(str(intent.stop_distance)),
                    price=execution_price,
                    leverage_cap=risk.leverage_cap,
                    available_margin=acct.available,
                    filters=filters,
                )
                if sizing.ok:
                    # Strategy distances are floats, so the raw prices land on
                    # sub-tick precision. Round before they reach the exchange or
                    # the protective stop is rejected (-1111) and the long is
                    # left naked until the emergency flatten.
                    stop_price = round_price(
                        execution_price - Decimal(str(intent.stop_distance)),
                        filters.tick_size,
                    )
                    tp_r, tp_frac = intent.tp_levels[0]
                    tp1_price = round_price(
                        execution_price + Decimal(str(tp_r)) * Decimal(str(intent.stop_distance)),
                        filters.tick_size,
                    )
                    await orders.open_long(
                        session,
                        sizing=sizing,
                        stop_price=stop_price,
                        tp1_price=tp1_price,
                        tp1_fraction=Decimal(str(tp_frac)),
                        strategy=strat.manifest.strategy_id,
                        strategy_release=strat.manifest.release,
                        strategy_interval=strat.manifest.market.interval,
                        bot_run_id=run.id,
                    )
                    actions.append("open_long")
            elif (
                isinstance(intent, EnterShort)
                and pos.qty == 0
                and entries_allowed
                and not state.halted_short
            ):
                sizing = _size_short_from_intent(
                    intent,
                    equity,
                    execution_price,
                    filters,
                    leverage_cap=risk.leverage_cap,
                    available_margin=acct.available,
                )
                if sizing.ok:
                    await orders.open_short(
                        session,
                        sizing=sizing,
                        strategy=strat.manifest.strategy_id,
                        strategy_release=strat.manifest.release,
                        strategy_interval=strat.manifest.market.interval,
                        bot_run_id=run.id,
                    )
                    actions.append("open_short")
            elif isinstance(intent, ExitAll) and pos.qty != 0:
                side = "LONG" if pos.qty > 0 else "SHORT"
                await orders.flatten(session, side=side, qty=pos.qty, reason=intent.reason)
                actions.append("exit_all")
            elif isinstance(intent, MoveStop) and pos.qty > 0 and trade is not None:
                moved = await orders.move_long_stop(
                    session,
                    trade=trade,
                    new_stop_price=Decimal(str(intent.price)),
                    remaining_qty=abs(pos.qty),
                    filters=filters,
                )
                if moved:
                    actions.append("move_stop")
            elif isinstance(intent, ResizeShort) and pos.qty < 0 and trade is not None:
                target_qty = clamp_qty(
                    equity * Decimal(str(intent.target_weight)) / execution_price,
                    filters,
                )
                current_qty = abs(pos.qty)
                drift = (
                    abs(target_qty - current_qty) / current_qty if current_qty > 0 else Decimal("0")
                )
                if (
                    target_qty > 0
                    and meets_min_notional(target_qty, execution_price, filters)
                    and drift > risk.short_resize_drift
                    and await orders.resize_short(
                        session,
                        trade=trade,
                        current_qty=pos.qty,
                        target_qty=target_qty,
                    )
                ):
                    actions.append("resize_short")
            elif isinstance(intent, TakePartial):
                await record_event(
                    session,
                    level="INFO",
                    category="trade",
                    message=f"TP level {intent.level_id} synchronized",
                    ref=f"trade:{trade.id}" if trade is not None else "take_partial",
                    payload={"level_id": intent.level_id},
                )
                actions.append("take_partial")
            elif isinstance(intent, Halt):
                await record_event(
                    session,
                    level="WARN",
                    category="breaker",
                    message=f"Strategy halt requested until {intent.until}",
                    ref=f"strategy_halt:{intent.until}",
                    payload={"until": intent.until},
                )
                actions.append("halt")

        stale_entry_intents = [
            intent for intent in intents if isinstance(intent, EnterLong | EnterShort)
        ]
        if not allow_new_entries and stale_entry_intents:
            await record_event(
                session,
                level="WARN",
                category="reconciliation",
                message="Stale entry signal skipped outside its validated execution window",
                ref=f"bot_run:{run.id}",
                payload={
                    "candle_open_time": decision_candle_at.isoformat(),
                    "strategy": run.strategy,
                    "intents": [type(intent).__name__ for intent in stale_entry_intents],
                },
            )
            actions.append("stale_entry_skipped")

        await self.write_equity_snapshot(
            session,
            exchange,
            snapshot_at=snapshot_at,
            long_month_pnl=monthly.long_pnl,
            short_month_pnl=monthly.short_pnl,
        )
        run.last_evaluated_candle_at = decision_candle_at
        return actions

    async def _monthly_risk_state(
        self,
        session: AsyncSession,
        *,
        environment: str,
        snapshot_at: dt.datetime,
        equity: Decimal,
        active_trade: Trade | None,
    ) -> MonthlyRiskState:
        """Advance independent monthly book P&L from persisted equity snapshots."""
        month_start = snapshot_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (
            month_start.replace(year=month_start.year + 1, month=1)
            if month_start.month == 12
            else month_start.replace(month=month_start.month + 1)
        )
        snapshots = (
            (
                await session.execute(
                    select(EquitySnapshot)
                    .where(
                        EquitySnapshot.environment == environment,
                        EquitySnapshot.ts >= month_start,
                        EquitySnapshot.ts < next_month,
                    )
                    .order_by(EquitySnapshot.ts)
                )
            )
            .scalars()
            .all()
        )
        month = month_start.strftime("%Y-%m")
        halted_long = await self._breaker_event_exists(session, book="LONG", month=month)
        halted_short = await self._breaker_event_exists(session, book="SHORT", month=month)
        if not snapshots:
            return MonthlyRiskState(
                month=month,
                month_start_equity=equity,
                long_pnl=Decimal("0"),
                short_pnl=Decimal("0"),
                halted_long=halted_long,
                halted_short=halted_short,
            )
        first = snapshots[0]
        month_start_equity = first.balance + first.unrealized_pnl
        existing = next((row for row in snapshots if row.ts == snapshot_at), None)
        if existing is not None:
            return MonthlyRiskState(
                month=month,
                month_start_equity=month_start_equity,
                long_pnl=existing.month_to_date_pnl,
                short_pnl=existing.sleeve_month_pnl,
                halted_long=halted_long,
                halted_short=halted_short,
            )
        previous = snapshots[-1]
        delta = equity - (previous.balance + previous.unrealized_pnl)
        long_pnl = previous.month_to_date_pnl
        short_pnl = previous.sleeve_month_pnl
        if active_trade is not None:
            if active_trade.side == "LONG":
                long_pnl += delta
            else:
                short_pnl += delta
        return MonthlyRiskState(
            month=month,
            month_start_equity=month_start_equity,
            long_pnl=long_pnl,
            short_pnl=short_pnl,
            halted_long=halted_long,
            halted_short=halted_short,
        )

    async def _breaker_event_exists(self, session: AsyncSession, *, book: str, month: str) -> bool:
        return (
            await session.execute(
                select(Event.id).where(Event.ref == f"breaker:{book}:{month}").limit(1)
            )
        ).scalar_one_or_none() is not None

    async def _trip_breaker(
        self,
        session: AsyncSession,
        *,
        run: BotRun,
        book: str,
        month: str,
        pnl: Decimal,
        month_start_equity: Decimal,
    ) -> None:
        await record_event(
            session,
            level="WARN",
            category="breaker",
            message=f"{book} monthly loss cap reached; halted until next month",
            ref=f"breaker:{book}:{month}",
            payload={
                "book": book,
                "month": month,
                "month_to_date_pnl": str(pnl),
                "month_start_equity": str(month_start_equity),
                "bot_run_id": run.id,
            },
        )
        from app.services.notify_config import notify_event

        await notify_event(
            session,
            kind="breaker",
            payload={
                "book": book,
                "pnl": str(pnl),
                "month": month,
            },
        )


def _size_short_from_intent(
    intent: EnterShort,
    equity: Decimal,
    price: Decimal,
    filters: SymbolFilters,
    *,
    leverage_cap: Decimal,
    available_margin: Decimal,
) -> SizingResult:
    """Size the short from the strategy's already-vol-scaled weight."""
    weight = Decimal(str(intent.weight))
    notional = equity * weight
    raw_qty = margin_capped_qty(notional / price, price, available_margin, leverage_cap)
    qty = clamp_qty(raw_qty, filters)
    if qty <= 0 or not meets_min_notional(qty, price, filters):
        return SizingResult(Decimal("0"), Decimal("0"), Decimal("0"), False, "below min")
    return SizingResult(qty, qty * price, (qty * price) / equity, True, "ok")


bot_service = BotService()
