"""OrderManager: translate strategy intents + sizing into exchange orders.

Owns idempotent client order IDs and DB persistence (orders + trades). Depends on
the Exchange protocol, so it is fully tested against a FakeExchange and validated
live against DEMO once credentials exist. All money Decimal.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Order, Trade
from app.execution.exchange import Exchange, OrderResult
from app.risk.sizing import SizingResult
from app.services.events import record_event

_log = get_logger("orders")


def new_client_order_id(prefix: str = "CP") -> str:
    """A unique, idempotent client order id (safe to retry the same placement)."""
    return f"{prefix}-{uuid.uuid4().hex[:20]}"


@dataclass(frozen=True)
class EmergencyExitRecord:
    """The fills that actually executed when a protective stop could not be placed.

    Passed out of ``open_long`` via :class:`ProtectiveStopFailed` so the caller can
    record them durably *after* rolling back its own poisoned transaction. It holds
    only plain values (not ORM rows bound to the failed session) so it survives the
    rollback intact.
    """

    entry: OrderResult
    exit_result: OrderResult | None
    qty: Decimal
    strategy: str
    environment: str
    bot_run_id: int | None
    stop_price: Decimal
    stop_error: str
    stop_error_type: str
    flatten_error: str | None

    @property
    def flattened(self) -> bool:
        """True when the emergency reduce-only exit confirmed (position is flat)."""
        return self.exit_result is not None


class ProtectiveStopFailed(RuntimeError):
    """A long entry filled but its protective stop could not be placed.

    Carries the executed fills (:class:`EmergencyExitRecord`) so the trading loop
    can durably persist them once it has rolled back the failed decision — the
    entry order was flushed into that same session and must be re-recorded from a
    clean transaction to avoid a self-deadlock on the unique ``client_order_id``.
    """

    def __init__(self, message: str, *, record: EmergencyExitRecord) -> None:
        super().__init__(message)
        self.record = record


class OrderManager:
    """Places and records orders for one symbol via an Exchange."""

    def __init__(
        self, exchange: Exchange, symbol: str = "BTCUSDT", environment: str = "DEMO"
    ) -> None:
        self._ex = exchange
        self._symbol = symbol
        self._env = environment

    async def open_long(
        self,
        session: AsyncSession,
        *,
        sizing: SizingResult,
        stop_price: Decimal,
        tp1_price: Decimal,
        tp1_fraction: Decimal,
        strategy: str,
        bot_run_id: int | None = None,
    ) -> Trade:
        """MARKET entry + STOP_MARKET protective stop + LIMIT TP1 (all reduce-only)."""
        entry = await self._ex.place_market(
            self._symbol, "BUY", sizing.qty, client_order_id=new_client_order_id("CPL")
        )
        trade = await self._persist_trade(session, "LONG", entry, sizing.qty, strategy, bot_run_id)
        await self._persist_order(session, entry, trade.id, "MARKET", reduce_only=False)

        try:
            stop = await self._ex.place_stop_market(
                self._symbol,
                "SELL",
                sizing.qty,
                stop_price,
                client_order_id=new_client_order_id("CPS"),
            )
        except Exception as stop_error:
            # Capture the real rejection reason at the source — the caller only
            # sees a ProtectiveStopFailed, so without this the underlying exchange
            # error (e.g. -2021 "would immediately trigger", a transient 5xx) is
            # lost. The executed fills travel on the exception for durable recording.
            _log.error(
                "protective_stop_failed",
                symbol=self._symbol,
                stop_price=str(stop_price),
                qty=str(sizing.qty),
                error=str(stop_error),
                error_type=type(stop_error).__name__,
            )
            try:
                await self._ex.cancel_all(self._symbol)
                emergency = await self._ex.place_market(
                    self._symbol,
                    "SELL",
                    sizing.qty,
                    client_order_id=new_client_order_id("CP-EMERGENCY"),
                    reduce_only=True,
                )
            except Exception as flatten_error:
                # Money-safety compromised: a long may remain open with no stop.
                _log.critical(
                    "emergency_flatten_failed",
                    symbol=self._symbol,
                    qty=str(sizing.qty),
                    error=str(flatten_error),
                    error_type=type(flatten_error).__name__,
                )
                raise ProtectiveStopFailed(
                    "protective stop failed and emergency flatten was not confirmed",
                    record=self._emergency_record(
                        entry,
                        None,
                        sizing.qty,
                        strategy,
                        bot_run_id,
                        stop_price,
                        stop_error,
                        flatten_error,
                    ),
                ) from flatten_error
            raise ProtectiveStopFailed(
                "protective stop failed; long was emergency-flattened",
                record=self._emergency_record(
                    entry,
                    emergency,
                    sizing.qty,
                    strategy,
                    bot_run_id,
                    stop_price,
                    stop_error,
                    None,
                ),
            ) from stop_error
        await self._persist_order(
            session, stop, trade.id, "STOP_MARKET", reduce_only=True, stop_price=stop_price
        )

        tp_qty = _round_to(sizing.qty * tp1_fraction, sizing.qty)
        tp1 = await self._ex.place_take_profit(
            self._symbol,
            "SELL",
            tp_qty,
            tp1_price,
            client_order_id=new_client_order_id("CPT"),
        )
        await self._persist_order(
            session, tp1, trade.id, "LIMIT", reduce_only=True, price=tp1_price
        )
        await record_event(
            session,
            level="INFO",
            category="trade",
            message=f"LONG opened {sizing.qty} {self._symbol} @ {entry.avg_price}",
            ref=f"trade:{trade.id}",
            payload={
                "qty": str(sizing.qty),
                "entry": str(entry.avg_price),
                "stop": str(stop_price),
                "tp1": str(tp1_price),
            },
        )
        from app.services.notify_config import notify_event

        await notify_event(
            session,
            kind="trade_opened",
            payload={
                "side": "LONG",
                "qty": str(sizing.qty),
                "price": str(entry.avg_price),
                "risk_context": f"Stop {stop_price}, TP1 {tp1_price}",
                "environment": self._env,
            },
        )
        return trade

    async def open_short(
        self,
        session: AsyncSession,
        *,
        sizing: SizingResult,
        strategy: str,
        bot_run_id: int | None = None,
    ) -> Trade:
        """MARKET short entry. No price stop by validated design (size-managed)."""
        entry = await self._ex.place_market(
            self._symbol, "SELL", sizing.qty, client_order_id=new_client_order_id("CPSH")
        )
        trade = await self._persist_trade(session, "SHORT", entry, sizing.qty, strategy, bot_run_id)
        await self._persist_order(session, entry, trade.id, "MARKET", reduce_only=False)
        await record_event(
            session,
            level="INFO",
            category="trade",
            message=f"SHORT sleeve opened {sizing.qty} {self._symbol} @ {entry.avg_price} "
            f"({sizing.leverage:.2f}x, vol-scaled). No price stop.",
            ref=f"trade:{trade.id}",
            payload={
                "qty": str(sizing.qty),
                "entry": str(entry.avg_price),
                "leverage": str(sizing.leverage),
                "price_stop": None,
            },
        )
        from app.services.notify_config import notify_event

        await notify_event(
            session,
            kind="short_opened",
            payload={
                "qty": str(sizing.qty),
                "price": str(entry.avg_price),
                "weight": f"{sizing.leverage:.0%}",
            },
        )
        return trade

    async def flatten(
        self, session: AsyncSession, *, side: str, qty: Decimal, reason: str
    ) -> OrderResult:
        """Cancel resting orders and close the position at MARKET (reduce-only)."""
        await self._ex.cancel_all(self._symbol)
        close_side = "SELL" if side == "LONG" else "BUY"
        result = await self._ex.place_market(
            self._symbol,
            close_side,
            abs(qty),
            client_order_id=new_client_order_id("CPX"),
            reduce_only=True,
        )
        await record_event(
            session,
            level="INFO",
            category="trade",
            message=f"Flattened {side} {abs(qty)} {self._symbol} ({reason})",
            ref="flatten",
            payload={"side": side, "qty": str(abs(qty)), "reason": reason},
        )
        return result

    async def kill(self, session: AsyncSession) -> int:
        """Kill switch: cancel all orders and flatten any position at market."""
        cancelled = await self._ex.cancel_all(self._symbol)
        pos = await self._ex.get_position(self._symbol)
        if pos.qty != 0:
            side = "LONG" if pos.qty > 0 else "SHORT"
            await self.flatten(session, side=side, qty=pos.qty, reason="kill switch")
        await record_event(
            session,
            level="WARN",
            category="bot",
            message="Kill switch: orders cancelled and positions flattened",
            ref="kill",
            payload={"cancelled_orders": cancelled, "position": str(pos.qty)},
        )
        return cancelled

    # --- persistence ---

    def _emergency_record(
        self,
        entry: OrderResult,
        exit_result: OrderResult | None,
        qty: Decimal,
        strategy: str,
        bot_run_id: int | None,
        stop_price: Decimal,
        stop_error: BaseException,
        flatten_error: BaseException | None,
    ) -> EmergencyExitRecord:
        """Snapshot the executed fills for durable recording by the caller."""
        return EmergencyExitRecord(
            entry=entry,
            exit_result=exit_result,
            qty=qty,
            strategy=strategy,
            environment=self._env,
            bot_run_id=bot_run_id,
            stop_price=stop_price,
            stop_error=str(stop_error),
            stop_error_type=type(stop_error).__name__,
            flatten_error=str(flatten_error) if flatten_error is not None else None,
        )

    async def _persist_trade(
        self,
        session: AsyncSession,
        side: str,
        entry: OrderResult,
        qty: Decimal,
        strategy: str,
        bot_run_id: int | None,
    ) -> Trade:
        trade = Trade(
            opened_at=dt.datetime.now(dt.UTC),
            side=side,
            entry_px=entry.avg_price if entry.avg_price > 0 else Decimal("0"),
            qty=qty,
            strategy=strategy,
            environment=self._env,
            bot_run_id=bot_run_id,
        )
        session.add(trade)
        await session.flush()
        return trade

    async def _persist_order(
        self,
        session: AsyncSession,
        result: OrderResult,
        trade_id: int,
        order_type: str,
        *,
        reduce_only: bool,
        price: Decimal | None = None,
        stop_price: Decimal | None = None,
    ) -> None:
        await _persist_order_row(
            session,
            result,
            trade_id,
            order_type,
            reduce_only=reduce_only,
            price=price,
            stop_price=stop_price,
        )


async def _persist_order_row(
    session: AsyncSession,
    result: OrderResult,
    trade_id: int,
    order_type: str,
    *,
    reduce_only: bool,
    price: Decimal | None = None,
    stop_price: Decimal | None = None,
) -> None:
    """Persist one order row from an exchange result (caller owns the transaction)."""
    session.add(
        Order(
            binance_order_id=result.exchange_order_id or None,
            client_order_id=result.client_order_id,
            trade_id=trade_id,
            type=order_type,
            status=result.status,
            price=price,
            stop_price=stop_price,
            qty=result.filled_qty if result.filled_qty > 0 else Decimal("0"),
            reduce_only=reduce_only,
            placed_at=dt.datetime.now(dt.UTC),
            filled_at=dt.datetime.now(dt.UTC) if result.status == "FILLED" else None,
            raw_json=result.raw,
        )
    )
    await session.flush()


async def persist_emergency_exit(session: AsyncSession, record: EmergencyExitRecord) -> None:
    """Durably record the fills that executed when a protective stop could not be placed.

    Call with a *clean* session — after the failed decision's transaction is rolled
    back — because recording these fills is how the audit/PnL trail survives that
    rollback (BSD G5). Re-recording the entry from a fresh transaction also avoids a
    self-deadlock on the unique ``client_order_id`` that a concurrent session would hit.
    The caller owns the commit.

    When the emergency flatten confirmed, the trade is recorded closed (net flat) so
    ``_expected_position`` stays consistent with the flat exchange. When it did not
    confirm, the trade is left open so the next reconciliation treats the position as
    possibly still held and keeps the bot in safe mode.
    """
    flattened = record.flattened
    now = dt.datetime.now(dt.UTC)
    entry_px = record.entry.avg_price if record.entry.avg_price > 0 else Decimal("0")
    exit_px = (
        record.exit_result.avg_price
        if record.exit_result is not None and record.exit_result.avg_price > 0
        else None
    )
    realized = (exit_px - entry_px) * record.qty if exit_px is not None else None
    trade = Trade(
        opened_at=now,
        closed_at=now if flattened else None,
        side="LONG",
        entry_px=entry_px,
        exit_px=exit_px,
        qty=record.qty,
        realized_pnl=realized,
        exit_reason=(
            "protective_stop_failed_emergency_exit"
            if flattened
            else "protective_stop_failed_flatten_unconfirmed"
        ),
        strategy=record.strategy,
        environment=record.environment,
        bot_run_id=record.bot_run_id,
    )
    session.add(trade)
    await session.flush()
    await _persist_order_row(session, record.entry, trade.id, "MARKET", reduce_only=False)
    if record.exit_result is not None:
        await _persist_order_row(session, record.exit_result, trade.id, "MARKET", reduce_only=True)
    await record_event(
        session,
        level="ERROR",
        category="trade" if flattened else "reconciliation",
        message=(
            "Protective stop failed; long emergency-flattened"
            if flattened
            else "Protective stop failed AND emergency flatten unconfirmed "
            "— position may be unprotected"
        ),
        ref=f"trade:{trade.id}",
        payload={
            "qty": str(record.qty),
            "entry": str(entry_px),
            "stop": str(record.stop_price),
            "exit": str(exit_px) if exit_px is not None else None,
            "flattened": flattened,
            "stop_error": record.stop_error,
            "stop_error_type": record.stop_error_type,
            "flatten_error": record.flatten_error,
        },
    )


def _round_to(value: Decimal, reference: Decimal) -> Decimal:
    """Round value to the same number of decimal places as reference's step."""
    exp = reference.as_tuple().exponent
    if isinstance(exp, int) and exp < 0:
        return value.quantize(Decimal(1).scaleb(exp))
    return value
