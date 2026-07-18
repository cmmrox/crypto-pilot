"""Background candle-ingest service.

Backfills closed candles on startup, then wakes shortly after each 4h close to
ingest the newly-closed candle and record a heartbeat. This gives gap-free
closed-candle ingest (Stage 2 exit criterion). Live intrabar marks via WebSocket
arrive in Stage 5.
"""

from __future__ import annotations

import asyncio
import contextlib

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.scheduler import DeadMan, seconds_until_next_close, utc_now
from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.execution import candles as candle_svc
from app.execution.binance_client import BinanceClient
from app.services.events import record_event
from app.services.settings_store import get_settings_row

_log = get_logger("ingest")

SYMBOL = "BTCUSDT"
INTERVAL = "4h"
POST_CLOSE_DELAY_S = 8  # let the exchange finalize the candle before we fetch


class CandleIngestService:
    """Owns the ingest loop as an asyncio task."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._dead_man = DeadMan(INTERVAL)
        self._stop = asyncio.Event()

    @property
    def dead_man(self) -> DeadMan:
        return self._dead_man

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._stop.clear()
        await self._ingest_once(reason="startup")
        self._task = asyncio.create_task(self._run(), name="candle-ingest")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            delay = seconds_until_next_close(utc_now(), INTERVAL) + POST_CLOSE_DELAY_S
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
                return  # stop requested
            except TimeoutError:
                pass  # a candle just closed
            await self._ingest_once(reason="candle_close")
            await self._dead_man_check()

    async def _dead_man_check(self) -> None:
        """If a 4h tick was missed past grace, alert the owner by SMS (once)."""
        if not self._dead_man.is_overdue(utc_now()):
            return
        try:
            async with get_sessionmaker()() as session:
                from app.services.notify_config import notify_event

                await record_event(
                    session, level="ERROR", category="error",
                    message="Dead-man's switch: missed 4h candle tick",
                    ref="dead_man", payload={"last_tick": str(self._dead_man.last_tick)},
                )
                await notify_event(
                    session, kind="error",
                    payload={"error": "missed 4h candle tick (dead-man)"},
                )
                await session.commit()
        except Exception as exc:
            _log.error("dead_man_alert_failed", error=str(exc))

    async def _ingest_once(self, *, reason: str) -> None:
        try:
            async with get_sessionmaker()() as session:
                settings_row = await get_settings_row(session)
                env = settings_row.active_environment
                async with BinanceClient(env) as client:
                    await candle_svc.backfill(session, client, SYMBOL, INTERVAL, limit=500)
                gaps = await candle_svc.detect_gaps(session, SYMBOL, INTERVAL)
                self._dead_man.beat(utc_now())
                await record_event(
                    session,
                    level="INFO" if not gaps else "WARN",
                    category="system",
                    message=f"Candle ingest ({reason}) — {len(gaps)} gap(s)",
                    ref="ingest",
                    payload={"reason": reason, "gaps": len(gaps), "environment": env},
                )
                await session.commit()
                # Drive the bot on a real candle close (not on startup catch-up).
                if reason == "candle_close":
                    await self._drive_bot(session)
        except Exception as exc:
            _log.error("ingest_failed", reason=reason, error=str(exc))

    async def _drive_bot(self, session: AsyncSession) -> None:
        """If the bot is running and credentials exist, evaluate the closed candle."""
        from sqlalchemy import select

        from app.bot.service import bot_service
        from app.bot.state import BotStatus
        from app.db.models import Candle
        from app.services.execution_service import NotConfiguredError, execution_context

        snap = await bot_service.status(session)
        if snap.status != BotStatus.RUNNING:
            return
        candles = (
            (
                await session.execute(
                    select(Candle)
                    .where(Candle.symbol == SYMBOL, Candle.interval == INTERVAL)
                    .order_by(Candle.open_time.desc())
                    .limit(400)
                )
            )
            .scalars()
            .all()
        )
        candles = list(reversed(candles))
        try:
            async with execution_context(session) as ctx:
                actions = await bot_service.evaluate_once(
                    session, ctx.exchange, ctx.orders, candles=candles
                )
                if actions:
                    _log.info("bot_actions", actions=actions)
                await session.commit()
        except NotConfiguredError:
            return
        except Exception as exc:
            _log.error("bot_drive_failed", error=str(exc))


ingest_service = CandleIngestService()
