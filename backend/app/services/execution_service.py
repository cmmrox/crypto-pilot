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

from app.core.config import get_settings
from app.execution.binance_client import BinanceClient
from app.execution.binance_exchange import BinanceExchange
from app.execution.live_readiness import LiveReadiness, verify_live_readiness
from app.execution.orders import OrderManager
from app.services import credentials as cred_svc
from app.services.settings_store import get_settings_row
from app.strategies import MarketSpec, get_strategy


class NotConfiguredError(Exception):
    """No Binance credentials configured for the active environment."""


class LiveTradingBlockedError(RuntimeError):
    """The release gate or current Binance account truth blocks LIVE start."""


@dataclass
class ExecutionContext:
    environment: str
    market: MarketSpec
    exchange: BinanceExchange
    orders: OrderManager


async def require_live_ready(
    session: AsyncSession,
    *,
    require_flat: bool,
) -> LiveReadiness:
    """Re-read LIVE credentials and Binance controls immediately before activation."""
    runtime = get_settings()
    if not (runtime.live_trading_approved and runtime.live_key_permissions_verified):
        raise LiveTradingBlockedError(
            "LIVE is locked until owner approval and key-permission verification are enabled"
        )
    settings_row = await get_settings_row(session)
    strategy = get_strategy(settings_row.active_strategy)
    leverage = strategy.manifest.risk.leverage_cap
    if leverage != leverage.to_integral_value():
        raise LiveTradingBlockedError("active strategy leverage cap must be a whole number")
    creds = await cred_svc.get_decrypted(session, environment="LIVE", service="binance")
    if creds is None:
        raise LiveTradingBlockedError("no Binance credentials configured for LIVE")
    async with BinanceClient("LIVE", api_key=creds[0], api_secret=creds[1]) as client:
        readiness = await verify_live_readiness(
            client,
            required_leverage=int(leverage),
            require_flat=require_flat,
        )
    if not readiness.ready:
        raise LiveTradingBlockedError("; ".join(readiness.issues))
    return readiness


@asynccontextmanager
async def execution_context(session: AsyncSession) -> AsyncIterator[ExecutionContext]:
    """Yield a ready Exchange + OrderManager for the active environment.

    Raises NotConfiguredError if Binance credentials are absent.
    """
    settings_row = await get_settings_row(session)
    env = settings_row.active_environment
    market = get_strategy(settings_row.active_strategy).manifest.market
    creds = await cred_svc.get_decrypted(session, environment=env, service="binance")
    if creds is None:
        raise NotConfiguredError(f"no Binance credentials configured for {env}")
    api_key, api_secret = creds
    async with BinanceClient(env, api_key=api_key, api_secret=api_secret) as client:
        exchange = BinanceExchange(client)
        yield ExecutionContext(
            environment=env,
            market=market,
            exchange=exchange,
            orders=OrderManager(
                exchange,
                symbol=market.symbol,
                environment=env,
            ),
        )
