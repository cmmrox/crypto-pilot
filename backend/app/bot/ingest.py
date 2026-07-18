"""Background candle-ingest service.

Backfills closed candles on startup, then wakes shortly after each 4h close to
ingest the newly-closed candle and record a heartbeat. This gives gap-free
closed-candle ingest (Stage 2 exit criterion). Live intrabar marks via WebSocket
arrive in Stage 5.
"""

from __future__ import annotations

import asyncio
import contextlib

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
        except Exception as exc:
            _log.error("ingest_failed", reason=reason, error=str(exc))


ingest_service = CandleIngestService()
