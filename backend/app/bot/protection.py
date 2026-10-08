"""Intrabar protection: user-stream wakeups plus bounded REST recovery.

Exchange truth, not websocket payloads, drives quantities and stop replacement.
Duplicate/reordered notifications therefore cannot repeat a partial or widen a stop.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

from websockets.asyncio.client import connect

from app.bot.coordination import trading_lock
from app.bot.service import bot_service
from app.bot.state import BotStatus
from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.execution.binance_client import WS_URLS, BinanceClient
from app.execution.trade_sync import sync_open_trade
from app.services import credentials as cred_svc
from app.services.events import record_event
from app.services.execution_service import NotConfiguredError, execution_context
from app.services.settings_store import get_settings_row

_log = get_logger("protection")
REST_RECOVERY_SECONDS = 5
KEEPALIVE_SECONDS = 25 * 60
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
                _log.error("protection_recovery_failed", error_type=type(exc).__name__)

    async def recover_once(self) -> None:
        async with trading_lock, get_sessionmaker()() as session:
            prior_status = (await bot_service.status(session)).status
            if prior_status == BotStatus.STOPPED:
                return
            try:
                async with execution_context(session) as ctx:
                    synced = await sync_open_trade(
                        session, ctx.exchange, environment=ctx.environment, symbol=ctx.market.symbol
                    )
                    if not synced.matched:
                        await bot_service.enter_safe_mode(
                            session, reason="intrabar account reconciliation mismatch"
                        )
                    await session.commit()
            except NotConfiguredError:
                await bot_service.enter_safe_mode(
                    session, reason="protection credentials unavailable"
                )
                await session.commit()
            except Exception as exc:
                await session.rollback()
                await bot_service.enter_safe_mode(
                    session, reason="intrabar protection recovery failed", alert=False
                )
                await record_event(
                    session,
                    level="ERROR",
                    category="reconciliation",
                    ref="protection_recovery",
                    message="Protection recovery failed; new entries blocked; recovery will retry",
                    payload={
                        "error_type": type(exc).__name__,
                        "event_time_ms": self._event_time_ms,
                    },
                )
                if prior_status != BotStatus.SAFE_MODE:
                    from app.services.notify_config import notify_event

                    await notify_event(
                        session,
                        kind="error",
                        payload={
                            "error": "Protection recovery failed; entries blocked; see event ledger"
                        },
                    )
                await session.commit()
                raise

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


protection_service = ProtectionService()
