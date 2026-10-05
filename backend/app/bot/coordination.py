"""Single-worker execution mutex, held through transaction commit/rollback.

The deployment runs one backend worker. Exchange mutations, lifecycle controls,
fill recovery and candle decisions must share this lock; read-only APIs do not.
"""

import asyncio
from collections.abc import AsyncIterator
from types import TracebackType
from typing import Annotated
from weakref import WeakKeyDictionary

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session


class TradingLock:
    """One mutex per event loop (also supports isolated pytest event loops)."""

    def __init__(self) -> None:
        self._locks: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
            WeakKeyDictionary()
        )

    async def __aenter__(self) -> None:
        lock = self._locks.setdefault(asyncio.get_running_loop(), asyncio.Lock())
        await lock.acquire()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._locks[asyncio.get_running_loop()].release()


trading_lock = TradingLock()


async def trading_session(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AsyncIterator[AsyncSession]:
    async with trading_lock:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
