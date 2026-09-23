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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.scheduler import INTERVAL_SECONDS
from app.bot.state import BotSnapshot, BotStatus
from app.core.logging import get_logger
from app.db.models import BotRun, Candle, EquitySnapshot, Event, Trade
from app.execution.exchange import AccountState, Exchange, Position
from app.execution.filters import SymbolFilters, clamp_qty, meets_min_notional, round_price
from app.execution.orders import OrderManager
from app.execution.reconcile import reconcile_position
from app.execution.trade_sync import SyncedTrade, sync_open_trade
from app.risk.breakers import evaluate_breaker
from app.risk.sizing import SizingResult, margin_capped_qty, size_by_risk
from app.services.events import record_event
from app.services.settings_store import get_settings_row
from app.strategies import (
    EnterLong,
    EnterShort,
    EnterShortStop,
    ExitAll,
    Halt,
    Intent,
    MoveStop,
    ResizeShort,
    RiskSpec,
    Strategy,
    TakePartial,
    TradeState,
    canonical_strategy_id,
    get_strategy,
)
from app.strategies.base import Candle as StratCandle
from app.telemetry.decisions import record_decision

_log = get_logger("bot")


@dataclass(frozen=True)
class MonthlyRiskState:
    month: str
    month_start_equity: Decimal
    long_pnl: Decimal
    short_pnl: Decimal
    halted_long: bool
    halted_short: bool


class _ReleaseTags(TypedDict):
    strategy: str
    strategy_release: str
    strategy_interval: str
    bot_run_id: int


@dataclass
class _BreakerOutcome:
    long_tripped: bool
    short_tripped: bool
    actions: list[str] = field(default_factory=list)
    flattened: bool = False


@dataclass
class _Decision:
    """One closed-candle decision's inputs, updated as its intents execute."""

    session: AsyncSession
    exchange: Exchange
    orders: OrderManager
    run: BotRun
    strategy: Strategy
    filters: SymbolFilters
    execution_price: Decimal
    account: AccountState
    equity: Decimal
    position: Position
    trade: Trade | None
    state: TradeState
    entries_allowed: bool
    actions: list[str]
    # Equity change caused by this decision's own orders (fees, slippage against the
    # mark), per book. Snapshots taken before the orders cannot see it.
    execution_pnl: dict[str, Decimal] = field(
        default_factory=lambda: {"LONG": Decimal("0"), "SHORT": Decimal("0")}
    )

    async def charge_execution(self, book: str) -> None:
        """Charge the order just placed to `book` and refresh the account after it."""
        self.account = await self.exchange.get_account()
        after = self.account.balance + self.account.unrealized_pnl
        self.execution_pnl[book] += after - self.equity
        self.equity = after

    def can_enter(self, *, halted: bool) -> bool:
        """New positions open only from flat, with entries allowed and the book live."""
        return self.position.qty == 0 and self.entries_allowed and not halted

    def release_tags(self) -> _ReleaseTags:
        manifest = self.strategy.manifest
        return _ReleaseTags(
            strategy=manifest.strategy_id,
            strategy_release=manifest.release,
            strategy_interval=manifest.market.interval,
            bot_run_id=self.run.id,
        )


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
        environment = settings_row.active_environment
        strategy = get_strategy(run.strategy)
        market = strategy.manifest.market
        decision_candle_at = candles[-1].open_time
        synced = await sync_open_trade(
            session,
            exchange,
            environment=environment,
            symbol=market.symbol,
        )
        if not synced.matched:
            return await self._block_on_mismatch(
                session,
                exchange,
                run=run,
                symbol=market.symbol,
                synced=synced,
                decision_candle_at=decision_candle_at,
            )

        previous_decision = run.last_evaluated_candle_at
        if previous_decision is not None and decision_candle_at <= previous_decision:
            return []
        if await self._guard_missed_decision(
            session,
            run=run,
            interval=market.interval,
            previous_decision=previous_decision,
            decision_candle_at=decision_candle_at,
        ):
            allow_new_entries = False

        account = await exchange.get_account()
        equity = account.balance + account.unrealized_pnl
        filters = await exchange.get_filters(market.symbol)
        execution_price = await exchange.get_mark_price(market.symbol)
        snapshot_at = decision_candle_at + dt.timedelta(seconds=INTERVAL_SECONDS[market.interval])
        monthly = await self._monthly_risk_state(
            session,
            environment=environment,
            snapshot_at=snapshot_at,
            equity=equity,
            active_trade=synced.trade,
        )
        breakers = await self._enforce_breakers(
            session,
            orders,
            run=run,
            risk=strategy.manifest.risk,
            monthly=monthly,
            position=synced.position,
        )
        if breakers.flattened:
            flattened = await exchange.get_account()
            book = "LONG" if synced.position.qty > 0 else "SHORT"
            await self._close_decision(
                session,
                exchange,
                run=run,
                monthly=monthly,
                snapshot_at=snapshot_at,
                decision_candle_at=decision_candle_at,
                execution_pnl={book: flattened.balance + flattened.unrealized_pnl - equity},
            )
            return breakers.actions

        strategy_candles = _strategy_candles(candles)
        state = await self._trade_state(
            session,
            run=run,
            decision_candle=candles[-1],
            synced=synced,
            equity=equity,
            monthly=monthly,
            breakers=breakers,
        )
        intents = strategy.on_candle(strategy_candles, state)
        entries_allowed = run.stop_reason != "safe_mode" and allow_new_entries
        record_decision(
            session,
            strategy=strategy,
            candles=strategy_candles,
            state=state,
            intents=intents,
            entries_allowed=entries_allowed,
            run_id=run.id,
            equity=equity,
            execution_price=execution_price,
        )

        decision = _Decision(
            session=session,
            exchange=exchange,
            orders=orders,
            run=run,
            strategy=strategy,
            filters=filters,
            execution_price=execution_price,
            account=account,
            equity=equity,
            position=synced.position,
            trade=synced.trade,
            state=state,
            entries_allowed=entries_allowed,
            actions=breakers.actions,
        )
        for intent in intents:
            handler = _INTENT_HANDLERS.get(type(intent))
            if handler is not None:
                await handler(self, decision, intent)

        await self._report_stale_entries(
            session,
            run=run,
            intents=intents,
            allow_new_entries=allow_new_entries,
            decision_candle_at=decision_candle_at,
            actions=decision.actions,
        )
        await self._close_decision(
            session,
            exchange,
            run=run,
            monthly=monthly,
            snapshot_at=snapshot_at,
            decision_candle_at=decision_candle_at,
            execution_pnl=decision.execution_pnl,
        )
        return decision.actions

    # --- Decision steps --------------------------------------------------------

    async def _block_on_mismatch(
        self,
        session: AsyncSession,
        exchange: Exchange,
        *,
        run: BotRun,
        symbol: str,
        synced: SyncedTrade,
        decision_candle_at: dt.datetime,
    ) -> list[str]:
        """Exchange and database disagree: enter safe mode instead of deciding."""
        reconciliation = await reconcile_position(
            exchange, symbol, expected_qty=synced.expected_qty
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

    async def _guard_missed_decision(
        self,
        session: AsyncSession,
        *,
        run: BotRun,
        interval: str,
        previous_decision: dt.datetime | None,
        decision_candle_at: dt.datetime,
    ) -> bool:
        """Return True, after entering safe mode and paging, if a close was skipped."""
        step = dt.timedelta(seconds=INTERVAL_SECONDS[interval])
        if previous_decision is None or decision_candle_at <= previous_decision + step:
            return False
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
                "interval": interval,
            },
        )
        from app.services.notify_config import notify_event

        await notify_event(
            session,
            kind="error",
            payload={
                "error": (
                    "missed closed-candle decision; stale entries blocked and bot entered safe mode"
                )
            },
        )
        return True

    async def _enforce_breakers(
        self,
        session: AsyncSession,
        orders: OrderManager,
        *,
        run: BotRun,
        risk: RiskSpec,
        monthly: MonthlyRiskState,
        position: Position,
    ) -> _BreakerOutcome:
        """Trip each book's monthly breaker independently and flatten that book."""
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
        outcome = _BreakerOutcome(long_tripped=long_trip, short_tripped=short_trip)
        if long_trip and not monthly.halted_long:
            await self._trip_breaker(
                session,
                run=run,
                book="LONG",
                month=monthly.month,
                pnl=monthly.long_pnl,
                month_start_equity=monthly.month_start_equity,
            )
            outcome.actions.append("halt_long")
            if position.qty > 0:
                await orders.flatten(
                    session,
                    side="LONG",
                    qty=position.qty,
                    reason="long monthly breaker",
                )
                outcome.actions.append("breaker_exit_long")
                outcome.flattened = True
        if short_trip and not monthly.halted_short:
            await self._trip_breaker(
                session,
                run=run,
                book="SHORT",
                month=monthly.month,
                pnl=monthly.short_pnl,
                month_start_equity=monthly.month_start_equity,
            )
            outcome.actions.append("halt_short")
            if position.qty < 0:
                await orders.flatten(
                    session,
                    side="SHORT",
                    qty=position.qty,
                    reason="short monthly breaker",
                )
                outcome.actions.append("breaker_exit_short")
                outcome.flattened = True
        return outcome

    async def _trade_state(
        self,
        session: AsyncSession,
        *,
        run: BotRun,
        decision_candle: Candle,
        synced: SyncedTrade,
        equity: Decimal,
        monthly: MonthlyRiskState,
        breakers: _BreakerOutcome,
    ) -> TradeState:
        """Advance the open trade's extremes and describe the account to the strategy."""
        position = synced.position
        trade = synced.trade
        short_weight = 0.0
        if position.qty < 0 and equity > 0:
            short_weight = float(abs(position.qty) * position.entry_price / equity)
        if trade is not None and trade.side == "LONG" and position.qty > 0:
            trade.highest_high = max(trade.highest_high or trade.entry_px, decision_candle.high)
        if trade is not None and trade.side == "SHORT" and position.qty < 0:
            trade.lowest_low = min(trade.lowest_low or trade.entry_px, decision_candle.low)
        last_long_closed_at = await _last_closed_at(session, run.environment, "LONG")
        last_short_closed_at = await _last_closed_at(session, run.environment, "SHORT")
        return TradeState(
            equity=float(equity),
            long_position=position.qty > 0,
            short_weight=short_weight,
            long_entry=(
                float(trade.entry_px) if trade is not None and trade.side == "LONG" else None
            ),
            long_stop=(
                float(synced.stop_price)
                if synced.stop_price is not None and trade is not None and trade.side == "LONG"
                else None
            ),
            highest_high=(
                float(trade.highest_high)
                if trade is not None and trade.highest_high is not None
                else None
            ),
            tp1_done=synced.tp1_done,
            last_long_closed_at_ms=_epoch_ms(last_long_closed_at),
            halted_long=monthly.halted_long or breakers.long_tripped,
            halted_short=monthly.halted_short or breakers.short_tripped,
            short_position=position.qty < 0,
            short_entry=(
                float(trade.entry_px) if trade is not None and trade.side == "SHORT" else None
            ),
            short_stop=(
                float(synced.stop_price)
                if synced.stop_price is not None and trade is not None and trade.side == "SHORT"
                else None
            ),
            lowest_low=(
                float(trade.lowest_low)
                if trade is not None and trade.lowest_low is not None
                else None
            ),
            last_short_closed_at_ms=_epoch_ms(last_short_closed_at),
        )

    async def _report_stale_entries(
        self,
        session: AsyncSession,
        *,
        run: BotRun,
        intents: list[Intent],
        allow_new_entries: bool,
        decision_candle_at: dt.datetime,
        actions: list[str],
    ) -> None:
        """Audit entry signals that arrived outside their validated execution window."""
        stale_entry_intents = [
            intent
            for intent in intents
            if isinstance(intent, EnterLong | EnterShort | EnterShortStop)
        ]
        if allow_new_entries or not stale_entry_intents:
            return
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

    async def _close_decision(
        self,
        session: AsyncSession,
        exchange: Exchange,
        *,
        run: BotRun,
        monthly: MonthlyRiskState,
        snapshot_at: dt.datetime,
        decision_candle_at: dt.datetime,
        execution_pnl: dict[str, Decimal] | None = None,
    ) -> None:
        """Snapshot equity for the monthly books and advance the decision cursor.

        Each book's month-to-date P&L includes what this decision's own orders cost
        it: the snapshot equity is taken after them, so the next decision's delta
        cannot see those costs.
        """
        costs = execution_pnl or {}
        await self.write_equity_snapshot(
            session,
            exchange,
            snapshot_at=snapshot_at,
            long_month_pnl=monthly.long_pnl + costs.get("LONG", Decimal("0")),
            short_month_pnl=monthly.short_pnl + costs.get("SHORT", Decimal("0")),
        )
        run.last_evaluated_candle_at = decision_candle_at

    # --- Intent handlers ---------------------------------------------------------
    #
    # One handler per intent in the architecture's vocabulary. Each applies its own
    # guard; a new intent needs a handler and an _INTENT_HANDLERS entry, nothing more.

    async def _enter_long(self, decision: _Decision, intent: EnterLong) -> None:
        if decision.can_enter(halted=decision.state.halted_long):
            await self._open_protected(decision, intent, side="LONG")

    async def _enter_short_with_stop(self, decision: _Decision, intent: EnterShortStop) -> None:
        if decision.can_enter(halted=decision.state.halted_short):
            await self._open_protected(decision, intent, side="SHORT")

    async def _open_protected(
        self,
        decision: _Decision,
        intent: EnterLong | EnterShortStop,
        *,
        side: str,
    ) -> None:
        """Open a stop-protected entry sized so a stop-out loses the risk budget."""
        risk = decision.strategy.manifest.risk
        stop_distance = Decimal(str(intent.stop_distance))
        # Stop-protected entries on either side draw on the release's one
        # risk-per-trade budget (RiskSpec.long_risk_pct).
        sizing = size_by_risk(
            equity=decision.equity,
            risk_pct=risk.long_risk_pct,
            stop_distance=stop_distance,
            price=decision.execution_price,
            leverage_cap=risk.leverage_cap,
            available_margin=decision.account.available,
            filters=decision.filters,
        )
        if not sizing.ok:
            return
        # The stop sits against the position and the target in its favour. Strategy
        # distances are floats, so round both to the tick before they reach the
        # exchange, or the protective stop is rejected (-1111) and the position is
        # left unprotected until the emergency flatten.
        direction = Decimal("1") if side == "LONG" else Decimal("-1")
        tp_r, tp_frac = intent.tp_levels[0]
        stop_price = round_price(
            decision.execution_price - direction * stop_distance, decision.filters.tick_size
        )
        tp1_price = round_price(
            decision.execution_price + direction * Decimal(str(tp_r)) * stop_distance,
            decision.filters.tick_size,
        )
        open_protected = (
            decision.orders.open_long if side == "LONG" else decision.orders.open_short_with_stop
        )
        await open_protected(
            decision.session,
            sizing=sizing,
            stop_price=stop_price,
            tp1_price=tp1_price,
            tp1_fraction=Decimal(str(tp_frac)),
            **decision.release_tags(),
        )
        await decision.charge_execution(side)
        decision.actions.append("open_long" if side == "LONG" else "open_short")

    async def _enter_short_sleeve(self, decision: _Decision, intent: EnterShort) -> None:
        """Open the stop-free, volatility-sized short sleeve (no price stop, by design)."""
        if not decision.can_enter(halted=decision.state.halted_short):
            return
        risk = decision.strategy.manifest.risk
        sizing = _size_short_from_intent(
            intent,
            decision.equity,
            decision.execution_price,
            decision.filters,
            leverage_cap=risk.leverage_cap,
            available_margin=decision.account.available,
        )
        if sizing.ok:
            await decision.orders.open_short(
                decision.session, sizing=sizing, **decision.release_tags()
            )
            await decision.charge_execution("SHORT")
            decision.actions.append("open_short")

    async def _exit_all(self, decision: _Decision, intent: ExitAll) -> None:
        if decision.position.qty == 0:
            return
        side = "LONG" if decision.position.qty > 0 else "SHORT"
        await decision.orders.flatten(
            decision.session, side=side, qty=decision.position.qty, reason=intent.reason
        )
        decision.actions.append("exit_all")
        # A reversal emits ExitAll followed by the opposite entry in the same
        # decision, so the entry guards must see the now-flat account. The account
        # refresh also matters: the closed position's initial margin was still locked
        # in the pre-exit snapshot, which would cap the reversal entry below its risk
        # budget.
        symbol = decision.strategy.manifest.market.symbol
        decision.position = await decision.exchange.get_position(symbol)
        await decision.charge_execution(side)
        decision.trade = None

    async def _move_stop(self, decision: _Decision, intent: MoveStop) -> None:
        if decision.position.qty == 0 or decision.trade is None:
            return
        move = (
            decision.orders.move_long_stop
            if decision.position.qty > 0
            else decision.orders.move_short_stop
        )
        moved = await move(
            decision.session,
            trade=decision.trade,
            new_stop_price=Decimal(str(intent.price)),
            remaining_qty=abs(decision.position.qty),
            filters=decision.filters,
        )
        if moved:
            decision.actions.append("move_stop")

    async def _resize_short(self, decision: _Decision, intent: ResizeShort) -> None:
        if decision.position.qty >= 0 or decision.trade is None:
            return
        target_qty = clamp_qty(
            decision.equity * Decimal(str(intent.target_weight)) / decision.execution_price,
            decision.filters,
        )
        current_qty = abs(decision.position.qty)
        drift = abs(target_qty - current_qty) / current_qty if current_qty > 0 else Decimal("0")
        if (
            target_qty > 0
            and meets_min_notional(target_qty, decision.execution_price, decision.filters)
            and drift > decision.strategy.manifest.risk.short_resize_drift
            and await decision.orders.resize_short(
                decision.session,
                trade=decision.trade,
                current_qty=decision.position.qty,
                target_qty=target_qty,
            )
        ):
            await decision.charge_execution("SHORT")
            decision.actions.append("resize_short")

    async def _take_partial(self, decision: _Decision, intent: TakePartial) -> None:
        await record_event(
            decision.session,
            level="INFO",
            category="trade",
            message=f"TP level {intent.level_id} synchronized",
            ref=f"trade:{decision.trade.id}" if decision.trade is not None else "take_partial",
            payload={"level_id": intent.level_id},
        )
        decision.actions.append("take_partial")

    async def _halt(self, decision: _Decision, intent: Halt) -> None:
        await record_event(
            decision.session,
            level="WARN",
            category="breaker",
            message=f"Strategy halt requested until {intent.until}",
            ref=f"strategy_halt:{intent.until}",
            payload={"until": intent.until},
        )
        decision.actions.append("halt")

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
        halted_long = await self._breaker_event_exists(
            session, book="LONG", month=month, environment=environment
        )
        halted_short = await self._breaker_event_exists(
            session, book="SHORT", month=month, environment=environment
        )
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
        # The first snapshot is taken after that decision's orders and records their
        # cost in its book P&L; adding it back gives the equity the month began with.
        month_start_equity = (
            first.balance + first.unrealized_pnl - first.month_to_date_pnl - first.sleeve_month_pnl
        )
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

    async def _breaker_event_exists(
        self, session: AsyncSession, *, book: str, month: str, environment: str
    ) -> bool:
        return (
            await session.execute(
                select(Event.id)
                .outerjoin(BotRun, BotRun.id == Event.payload_json["bot_run_id"].as_integer())
                .where(
                    Event.ref == f"breaker:{book}:{month}",
                    # Older events without an attributable run remain fail-closed.
                    (BotRun.environment == environment) | BotRun.id.is_(None),
                )
                .limit(1)
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


def _strategy_candles(candles: list[Candle]) -> list[StratCandle]:
    return [
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


async def _last_closed_at(session: AsyncSession, environment: str, side: str) -> dt.datetime | None:
    """When this environment's book on `side` last closed a trade (re-entry gating)."""
    return await session.scalar(
        select(Trade.closed_at)
        .where(
            Trade.environment == environment,
            Trade.side == side,
            Trade.closed_at.is_not(None),
        )
        .order_by(Trade.closed_at.desc())
        .limit(1)
    )


def _epoch_ms(moment: dt.datetime | None) -> int | None:
    return int(moment.timestamp() * 1000) if moment is not None else None


# Intent vocabulary (ARCHITECTURE.md §3) -> handler. Dispatch is by exact type: the
# intents are independent classes joined by the `Intent` union.
_IntentHandler = Callable[[BotService, _Decision, Any], Awaitable[None]]
_INTENT_HANDLERS: dict[type[Any], _IntentHandler] = {
    EnterLong: BotService._enter_long,
    EnterShortStop: BotService._enter_short_with_stop,
    EnterShort: BotService._enter_short_sleeve,
    ExitAll: BotService._exit_all,
    MoveStop: BotService._move_stop,
    ResizeShort: BotService._resize_short,
    TakePartial: BotService._take_partial,
    Halt: BotService._halt,
}


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
