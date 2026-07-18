"""Execution service: resolve stored credentials into a ready Exchange + OrderManager.

This is the seam the bot loop (Stage 5) uses to act. Credentials are read from the
encrypted store; if none are configured the service reports unconfigured rather than
raising, so the dashboard can guide the owner.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.execution.binance_client import BinanceClient
from app.execution.binance_exchange import BinanceExchange
from app.execution.orders import OrderManager
from app.services import credentials as cred_svc
from app.services.settings_store import get_settings_row


class NotConfiguredError(Exception):
    """No Binance credentials configured for the active environment."""


@dataclass
class ExecutionContext:
    environment: str
    exchange: BinanceExchange
    orders: OrderManager


@asynccontextmanager
async def execution_context(session: AsyncSession) -> AsyncIterator[ExecutionContext]:
    """Yield a ready Exchange + OrderManager for the active environment.

    Raises NotConfiguredError if Binance credentials are absent.
    """
    settings_row = await get_settings_row(session)
    env = settings_row.active_environment
    creds = await cred_svc.get_decrypted(session, environment=env, service="binance")
    if creds is None:
        raise NotConfiguredError(f"no Binance credentials configured for {env}")
    api_key, api_secret = creds
    async with BinanceClient(env, api_key=api_key, api_secret=api_secret) as client:
        exchange = BinanceExchange(client)
        yield ExecutionContext(
            environment=env,
            exchange=exchange,
            orders=OrderManager(exchange, environment=env),
        )
