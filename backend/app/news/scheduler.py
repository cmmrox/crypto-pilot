"""Daily news scheduler: wakes once per day near the configured local time and
publishes a briefing (if Codex is connected). Failures never crash the loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt

from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.news import service as news_svc
from app.news.codex_auth import codex_auth
from app.services.settings_store import get_settings_row

_log = get_logger("news_scheduler")


def _seconds_until(hhmm: str, now: dt.datetime) -> float:
    """Seconds from now until the next UTC occurrence of HH:MM."""
    try:
        hh, mm = (int(x) for x in hhmm.split(":"))
    except ValueError:
        hh, mm = 6, 30
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return (target - now).total_seconds()


class NewsScheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="news-scheduler")

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
                news_time = (await get_settings_row(session)).news_time
            delay = _seconds_until(news_time, dt.datetime.now(dt.UTC))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
                return
            except TimeoutError:
                pass
            await self._publish()

    async def _publish(self) -> None:
        try:
            if not await codex_auth.is_authenticated():
                _log.info("news_skip_unauthenticated")
                return
            async with get_sessionmaker()() as session:
                await news_svc.refresh_briefing(session)
                await session.commit()
        except Exception as exc:
            _log.error("news_publish_failed", error=str(exc))


news_scheduler = NewsScheduler()
