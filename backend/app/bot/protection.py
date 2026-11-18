"""Intrabar protection: user-stream wakeups plus bounded REST recovery.

Exchange truth, not websocket payloads, drives quantities and stop replacement.
Duplicate/reordered notifications therefore cannot repeat a partial or widen a stop.

A check that fails only because Binance could not serve a read is retried by the
next pass: the protective orders rest on the exchange, so protection does not depend
on it. Safe mode follows a streak of such failures, and follows at once any other
failure, including one after the check placed or cancelled an order.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from websockets.asyncio.client import connect

from app.bot.coordination import trading_lock
from app.bot.service import bot_service
from app.bot.state import BotStatus
from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.execution.binance_client import WS_URLS, BinanceClient, BinanceError
from app.execution.exchange import (
    AccountState,
    Exchange,
    Fill,
    FundingIncome,
    OrderResult,
    Position,
)
from app.execution.filters import SymbolFilters
from app.execution.trade_sync import sync_open_trade
from app.services import credentials as cred_svc
from app.services.events import record_event
from app.services.execution_service import NotConfiguredError, execution_context
from app.services.settings_store import get_settings_row

_log = get_logger("protection")
REST_RECOVERY_SECONDS = 5
KEEPALIVE_SECONDS = 25 * 60
# Consecutive failed passes (about 5 s apart) tolerated before safe mode when each
# failure is a transient read failure and no order was placed or cancelled.
SAFE_MODE_AFTER_TRANSIENT_FAILURES = 3
_ERROR_TEXT_LIMIT = 300
WAKE_EVENTS = {
    "ORDER_TRADE_UPDATE",
    "ALGO_UPDATE",
    "ACCOUNT_UPDATE",
    "CONDITIONAL_ORDER_TRIGGER_REJECT",
}


class ProtectionService:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[None]] = []
        self._wake = asyncio.Event()
        self._event_time_ms: int | None = None
        self._failures = 0

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._recover_loop(), name="protection-rest"),
            asyncio.create_task(self._stream_loop(), name="protection-stream"),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    def observe(self, event: dict[str, object]) -> bool:
        if event.get("e") not in WAKE_EVENTS:
            return False
        stamp = event.get("E")
        self._event_time_ms = int(str(stamp)) if stamp is not None else None
        self._wake.set()
        return True

    async def _recover_loop(self) -> None:
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), REST_RECOVERY_SECONDS)
            self._wake.clear()
            try:
                await self.recover_once()
            except Exception as exc:
                # Never log websocket URLs, listen keys, credential-bearing errors.
                _log.error("protection_recovery_failed", **failure_fields(exc))

    async def recover_once(self) -> None:
        async with trading_lock, get_sessionmaker()() as session:
            prior_status = (await bot_service.status(session)).status
            if prior_status == BotStatus.STOPPED:
                self._failures = 0
                return
            watched: _ActionWatch | None = None
            try:
                async with execution_context(session) as ctx:
                    watched = _ActionWatch(ctx.exchange)
                    synced = await sync_open_trade(
                        session, watched, environment=ctx.environment, symbol=ctx.market.symbol
                    )
                    if not synced.matched:
                        await bot_service.enter_safe_mode(
                            session, reason="intrabar account reconciliation mismatch"
                        )
                    await session.commit()
                self._failures = 0
            except NotConfiguredError:
                await bot_service.enter_safe_mode(
                    session, reason="protection credentials unavailable"
                )
                await session.commit()
            except Exception as exc:
                await session.rollback()
                acted = watched is not None and watched.acted
                await self._handle_failure(session, exc, acted=acted, prior_status=prior_status)

    async def _handle_failure(
        self, session: AsyncSession, exc: Exception, *, acted: bool, prior_status: BotStatus
    ) -> None:
        """Tolerate a short streak of transient read failures; otherwise block entries."""
        self._failures += 1
        transient = isinstance(exc, BinanceError) and exc.transient
        payload: dict[str, Any] = {
            **failure_fields(exc),
            "transient": transient,
            "mutation_attempted": acted,
            "consecutive_failures": self._failures,
            "threshold": SAFE_MODE_AFTER_TRANSIENT_FAILURES,
            "event_time_ms": self._event_time_ms,
        }
        if transient and not acted and self._failures < SAFE_MODE_AFTER_TRANSIENT_FAILURES:
            _log.warning("protection_recovery_transient_failure", **payload)
            if self._failures == 1:  # one ledger row per streak, not one per pass
                await record_event(
                    session,
                    level="WARN",
                    category="reconciliation",
                    ref="protection_recovery",
                    message=(
                        "Protection check failed on a transient Binance error; "
                        "retrying, entries still allowed"
                    ),
                    payload=payload,
                )
                await session.commit()
            return
        await bot_service.enter_safe_mode(
            session, reason="intrabar protection recovery failed", alert=False
        )
        await record_event(
            session,
            level="ERROR",
            category="reconciliation",
            ref="protection_recovery",
            message=(
                "Protection recovery failed; new entries blocked until the owner restarts the bot"
            ),
            payload=payload,
        )
        if prior_status != BotStatus.SAFE_MODE:
            from app.services.notify_config import notify_event

            await notify_event(
                session,
                kind="error",
                payload={"error": "Protection recovery failed; entries blocked; see event ledger"},
            )
        await session.commit()
        raise exc

    async def _stream_loop(self) -> None:
        while True:
            try:
                async with get_sessionmaker()() as session:
                    settings = await get_settings_row(session)
                    environment = settings.active_environment
                    credentials = await cred_svc.get_decrypted(
                        session, environment=environment, service="binance"
                    )
                if credentials is None:
                    await asyncio.sleep(10)
                    continue
                async with BinanceClient(
                    environment, api_key=credentials[0], api_secret=credentials[1]
                ) as client:
                    key = await client.start_user_stream()
                    try:
                        async with connect(
                            WS_URLS[environment] + "/ws/" + key, ping_interval=20, ping_timeout=20
                        ) as socket:
                            self._wake.set()  # restore fills missed during reconnect
                            keepalive_at = asyncio.get_running_loop().time() + KEEPALIVE_SECONDS
                            while True:
                                try:
                                    raw = await asyncio.wait_for(socket.recv(), 30)
                                except TimeoutError:
                                    raw = None
                                async with get_sessionmaker()() as session:
                                    settings = await get_settings_row(session)
                                    if settings.active_environment != environment:
                                        break
                                if raw is not None:
                                    event = json.loads(raw)
                                    if event.get("e") == "listenKeyExpired":
                                        break
                                    self.observe(event)
                                if asyncio.get_running_loop().time() >= keepalive_at:
                                    await client.keepalive_user_stream(key)
                                    keepalive_at = (
                                        asyncio.get_running_loop().time() + KEEPALIVE_SECONDS
                                    )
                    finally:
                        with contextlib.suppress(Exception):
                            await client.close_user_stream(key)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _log.warning("user_stream_reconnect", error_type=type(exc).__name__)
                self._wake.set()
                await asyncio.sleep(5)


def failure_fields(exc: BaseException) -> dict[str, Any]:
    """Allowlisted, credential-free description of a failed check.

    A Binance error carries the exchange's own message and the method and path
    only, never the signed query, so it is safe to persist.
    """
    fields: dict[str, Any] = {"error_type": type(exc).__name__}
    if isinstance(exc, BinanceError):
        fields.update(
            error=str(exc)[:_ERROR_TEXT_LIMIT],
            binance_status=exc.status,
            binance_code=exc.code,
            endpoint=exc.endpoint,
        )
    return fields


class _ActionWatch:
    """Delegate to the exchange, noting whether this check placed or cancelled."""

    def __init__(self, exchange: Exchange) -> None:
        self._exchange = exchange
        self.acted = False

    async def get_filters(self, symbol: str) -> SymbolFilters:
        return await self._exchange.get_filters(symbol)

    async def get_account(self) -> AccountState:
        return await self._exchange.get_account()

    async def get_position(self, symbol: str) -> Position:
        return await self._exchange.get_position(symbol)

    async def get_mark_price(self, symbol: str) -> Decimal:
        return await self._exchange.get_mark_price(symbol)

    async def get_open_orders(self, symbol: str) -> list[OrderResult]:
        return await self._exchange.get_open_orders(symbol)

    async def get_order(self, symbol: str, client_order_id: str) -> OrderResult:
        return await self._exchange.get_order(symbol, client_order_id)

    async def get_order_fills(self, symbol: str, exchange_order_id: str) -> list[Fill]:
        return await self._exchange.get_order_fills(symbol, exchange_order_id)

    async def get_funding_income(
        self, symbol: str, *, start_at: dt.datetime
    ) -> list[FundingIncome]:
        return await self._exchange.get_funding_income(symbol, start_at=start_at)

    async def place_market(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        *,
        client_order_id: str,
        reduce_only: bool = False,
    ) -> OrderResult:
        self.acted = True
        return await self._exchange.place_market(
            symbol, side, qty, client_order_id=client_order_id, reduce_only=reduce_only
        )

    async def place_stop_market(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        stop_price: Decimal,
        *,
        client_order_id: str,
        reduce_only: bool = True,
        working_type: str = "MARK_PRICE",
    ) -> OrderResult:
        self.acted = True
        return await self._exchange.place_stop_market(
            symbol,
            side,
            qty,
            stop_price,
            client_order_id=client_order_id,
            reduce_only=reduce_only,
            working_type=working_type,
        )

    async def place_take_profit(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        *,
        client_order_id: str,
        reduce_only: bool = True,
    ) -> OrderResult:
        self.acted = True
        return await self._exchange.place_take_profit(
            symbol, side, qty, price, client_order_id=client_order_id, reduce_only=reduce_only
        )

    async def cancel_all(self, symbol: str) -> int:
        self.acted = True
        return await self._exchange.cancel_all(symbol)

    async def cancel_order(self, symbol: str, client_order_id: str) -> OrderResult:
        self.acted = True
        return await self._exchange.cancel_order(symbol, client_order_id)

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        self.acted = True
        await self._exchange.set_leverage(symbol, leverage)


protection_service = ProtectionService()
