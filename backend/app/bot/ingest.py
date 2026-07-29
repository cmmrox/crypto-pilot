"""Background candle-ingest service.

Backfills closed candles on startup, then wakes shortly after each 4h close to
ingest the newly-closed candle and record a heartbeat. This gives gap-free
closed-candle ingest (Stage 2 exit criterion). Live intrabar marks via WebSocket
arrive in Stage 5.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.scheduler import DeadMan, seconds_until_next_close, utc_now
from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.execution import candles as candle_svc
from app.execution.binance_client import BinanceClient
from app.services.events import record_event
from app.services.settings_store import get_settings_row
from app.strategies import default_strategy, get_strategy

_log = get_logger("ingest")

POST_CLOSE_DELAY_S = 8  # let the exchange finalize the candle before we fetch
WORKER_HEARTBEAT_SECONDS = 5


class CandleIngestService:
    """Owns the ingest loop as an asyncio task."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._dead_man = DeadMan(default_strategy().manifest.market.interval)
        self._stop = asyncio.Event()
        self._worker_heartbeat_at: dt.datetime | None = None

    @property
    def dead_man(self) -> DeadMan:
        return self._dead_man

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def worker_heartbeat_at(self) -> dt.datetime | None:
        return self._worker_heartbeat_at

    def worker_heartbeat_age(self, now: dt.datetime) -> float | None:
        if self._worker_heartbeat_at is None:
            return None
        return max(0.0, (now - self._worker_heartbeat_at).total_seconds())

    async def start(self) -> None:
        self._stop.clear()
        await self._ingest_once(reason="startup")
        self._worker_heartbeat_at = utc_now()
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
            async with get_sessionmaker()() as session:
                settings_row = await get_settings_row(session)
                market = get_strategy(settings_row.active_strategy).manifest.market
            delay = seconds_until_next_close(utc_now(), market.interval) + POST_CLOSE_DELAY_S
            deadline = asyncio.get_running_loop().time() + delay
            while not self._stop.is_set():
                self._worker_heartbeat_at = utc_now()
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=min(WORKER_HEARTBEAT_SECONDS, remaining),
                    )
                    return
                except TimeoutError:
                    continue
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
                    session,
                    level="ERROR",
                    category="error",
                    message="Dead-man's switch: missed 4h candle tick",
                    ref="dead_man",
                    payload={"last_tick": str(self._dead_man.last_tick)},
                )
                await notify_event(
                    session,
                    kind="error",
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
                strategy = get_strategy(settings_row.active_strategy)
                market = strategy.manifest.market
                async with BinanceClient(env) as client:
                    if reason == "startup":
                        await candle_svc.backfill_history(
                            session,
                            client,
                            market.symbol,
                            market.interval,
                            bars=market.history_bars,
                        )
                    else:
                        await candle_svc.backfill(
                            session,
                            client,
                            market.symbol,
                            market.interval,
                            limit=500,
                        )
                gaps = await candle_svc.detect_gaps(session, market.symbol, market.interval)
                await record_event(
                    session,
                    level="INFO" if not gaps else "WARN",
                    category="system",
                    message=f"Candle ingest ({reason}) — {len(gaps)} gap(s)",
                    ref="ingest",
                    payload={
                        "reason": reason,
                        "gaps": len(gaps),
                        "environment": env,
                        "strategy": strategy.manifest.strategy_id,
                        "symbol": market.symbol,
                        "interval": market.interval,
                    },
                )
                await session.commit()
                # Drive the bot on a real candle close (not on startup catch-up).
                if reason == "candle_close" and not gaps:
                    await self._drive_bot(session)
                elif reason == "candle_close" and gaps:
                    await record_event(
                        session,
                        level="WARN",
                        category="reconciliation",
                        message="Trading decision blocked until candle gaps are repaired",
                        ref="candle_gap_block",
                        payload={"gaps": len(gaps)},
                    )
                    await session.commit()
                self._dead_man.beat(utc_now())
            # OTP retention housekeeping is deliberately isolated from the
            # trading transaction. A cleanup failure must never suppress a
            # closed-candle decision or its heartbeat.
            try:
                async with get_sessionmaker()() as cleanup_session:
                    from app.services.otp import cleanup_expired

                    await cleanup_expired(cleanup_session)
                    await cleanup_session.commit()
            except Exception as exc:
                _log.error("otp_cleanup_failed", error=str(exc))
        except Exception as exc:
            _log.error("ingest_failed", reason=reason, error=str(exc))

    async def _drive_bot(self, session: AsyncSession) -> None:
        """If the bot is running and credentials exist, evaluate the closed candle."""
        from sqlalchemy import select

        from app.bot.service import bot_service
        from app.bot.state import BotStatus
        from app.db.models import Candle
        from app.execution.orders import ProtectiveStopFailed, persist_emergency_exit
        from app.services.execution_service import NotConfiguredError, execution_context

        snap = await bot_service.status(session)
        # Safe mode blocks new entries, but protective position management and
        # reconciliation must continue on every closed candle.
        if snap.status == BotStatus.STOPPED:
            return
        strategy = get_strategy(snap.strategy)
        market = strategy.manifest.market
        candles = (
            (
                await session.execute(
                    select(Candle)
                    .where(
                        Candle.symbol == market.symbol,
                        Candle.interval == market.interval,
                    )
                    .order_by(Candle.open_time.desc())
                    .limit(market.history_bars)
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
            await bot_service.enter_safe_mode(
                session, reason="Binance credentials unavailable at candle close"
            )
            await session.commit()
        except ProtectiveStopFailed as exc:
            # A long filled but its protective stop could not be placed. Roll back the
            # poisoned decision transaction first (releasing the entry order's
            # uncommitted unique client_order_id), then durably re-record the fills
            # that actually executed on the exchange plus safe mode — one clean commit.
            await session.rollback()
            await bot_service.enter_safe_mode(
                session, reason="protective stop failed at candle close"
            )
            await persist_emergency_exit(session, exc.record)
            cause = exc.__cause__
            await record_event(
                session,
                level="ERROR",
                category="error",
                message="Closed-candle evaluation failed; bot entered safe mode",
                ref="bot_drive_failed",
                payload={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "cause": str(cause) if cause else None,
                    "cause_type": type(cause).__name__ if cause else None,
                    "flattened": exc.record.flattened,
                },
            )
            await session.commit()
            _log.error("bot_drive_failed", error=str(exc), cause=str(cause) if cause else None)
        except Exception as exc:
            await session.rollback()
            await bot_service.enter_safe_mode(session, reason="closed-candle evaluation failed")
            cause = exc.__cause__
            await record_event(
                session,
                level="ERROR",
                category="error",
                message="Closed-candle evaluation failed; bot entered safe mode",
                ref="bot_drive_failed",
                payload={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "cause": str(cause) if cause else None,
                    "cause_type": type(cause).__name__ if cause else None,
                },
            )
            await session.commit()
            _log.error("bot_drive_failed", error=str(exc), cause=str(cause) if cause else None)


ingest_service = CandleIngestService()
