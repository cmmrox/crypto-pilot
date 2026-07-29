"""Owner command-center projection for the four-second Overview poll.

This service combines read-only operational, market, strategy-explainability, news,
event, and account state. It never feeds data back into the trading path.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass, replace
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.ingest import WORKER_HEARTBEAT_SECONDS, ingest_service
from app.bot.scheduler import (
    INTERVAL_SECONDS,
    next_close_time,
    seconds_until_next_close,
    utc_now,
)
from app.bot.service import bot_service
from app.db.models import Briefing, Candle, Event, Trade
from app.execution import candles as candle_svc
from app.execution.binance_client import BinanceClient, BinanceError
from app.execution.binance_exchange import BinanceExchange
from app.risk.breakers import evaluate_breaker
from app.services import credentials as cred_svc
from app.services.settings_store import get_settings_row
from app.strategies import MarketSpec, RiskSpec, get_strategy
from app.strategies.base import (
    Candle as StrategyCandle,
)
from app.strategies.base import (
    Strategy,
    WatchRule,
)

FRESH_FOR_SECONDS = 10
SPARKLINE_POINTS = 24
RECENT_EVENTS = 3
PRICE_PLACES = Decimal("0.00000001")


@dataclass(frozen=True)
class PositionSnapshot:
    side: str
    qty: str
    entry_price: str
    mark_price: str | None
    unrealized_pnl: str
    leverage: str
    has_price_stop: bool


@dataclass(frozen=True)
class BreakerSnapshot:
    book: str
    month_to_date_pnl: str
    drawdown_pct: str
    progress_pct: str
    tripped: bool
    available: bool


@dataclass(frozen=True)
class EngineSnapshot:
    worker_running: bool
    worker_healthy: bool
    heartbeat_at: str | None
    heartbeat_age_seconds: float | None
    scheduler_alive: bool
    database: str
    ingest_last_tick: str | None
    ingest_overdue: bool
    candle_gaps: int


@dataclass(frozen=True)
class SparkPoint:
    ts: str
    close: str
    normalized_bps: int


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    interval: str
    reachable: bool
    mark_price: str | None
    price_change_24h_pct: str | None
    observed_at: str | None
    stale: bool
    next_close_utc: str
    seconds_to_next_close: float
    sparkline: list[SparkPoint]


@dataclass(frozen=True)
class WatchRuleSnapshot:
    key: str
    label: str
    status: str
    tone: str
    active: bool
    condition: str
    threshold_price: str | None
    distance: str | None
    distance_pct: str | None


@dataclass(frozen=True)
class StrategyWatchSnapshot:
    available: bool
    last_closed_at: str | None
    rules: list[WatchRuleSnapshot]
    disclaimer: str


@dataclass(frozen=True)
class ActivitySnapshot:
    ts: str
    label: str
    detail: str
    tone: str
    badge: str


@dataclass(frozen=True)
class BriefingBulletSnapshot:
    text: str
    source: str


@dataclass(frozen=True)
class BriefingSnapshot:
    available: bool
    sentiment: str | None
    generated_at: str | None
    bullets: list[BriefingBulletSnapshot]
    isolation_notice: str


@dataclass(frozen=True)
class OverviewSnapshot:
    checked_at: str
    fresh_for_seconds: int
    environment: str
    bot_status: str
    strategy: str
    exchange_reachable: bool
    account_available: bool
    balance: str
    equity: str
    unrealized_pnl: str
    position: PositionSnapshot | None
    breakers: list[BreakerSnapshot]
    month_realized_pnl: str
    engine: EngineSnapshot
    market: MarketSnapshot
    watch: StrategyWatchSnapshot
    activity: list[ActivitySnapshot]
    briefing: BriefingSnapshot


async def build_overview(session: AsyncSession) -> OverviewSnapshot:
    """Build one coherent command-center response for the current UTC instant."""
    settings_row = await get_settings_row(session)
    environment = settings_row.active_environment
    strategy_plugin = get_strategy(settings_row.active_strategy)
    strategy = strategy_plugin.manifest.strategy_id
    strategy_market = strategy_plugin.manifest.market
    strategy_risk = strategy_plugin.manifest.risk
    bot = await bot_service.status(session)
    candles = await _recent_candles(session, strategy_market)
    gaps = await candle_svc.detect_gaps(
        session,
        strategy_market.symbol,
        strategy_market.interval,
    )
    gap_count = len(gaps)
    for candle in candles:
        session.expunge(candle)
    await session.rollback()
    market, account = await asyncio.gather(
        _market_snapshot(environment, candles, strategy_market),
        _account_snapshot(session, environment, strategy_market.symbol),
    )
    if account.position is not None:
        account = replace(
            account,
            position=replace(account.position, mark_price=market.mark_price),
        )
    now = utc_now()
    breakers, month_realized = await _breaker_snapshots(
        session,
        now,
        account.equity,
        strategy_risk,
    )
    watch = _watch_snapshot(
        candles,
        market.mark_price,
        strategy_plugin,
    )
    engine = _engine_snapshot(now, gap_count)
    activity = await _activity_snapshots(session, engine, market)
    briefing = await _briefing_snapshot(session)

    return OverviewSnapshot(
        checked_at=now.isoformat(),
        fresh_for_seconds=FRESH_FOR_SECONDS,
        environment=environment,
        bot_status=bot.status.value,
        strategy=strategy,
        exchange_reachable=market.reachable,
        account_available=account.available,
        balance=_decimal(account.balance),
        equity=_decimal(account.equity),
        unrealized_pnl=_decimal(account.unrealized_pnl),
        position=account.position,
        breakers=breakers,
        month_realized_pnl=_decimal(month_realized),
        engine=engine,
        market=market,
        watch=watch,
        activity=activity,
        briefing=briefing,
    )


@dataclass(frozen=True)
class _AccountSnapshot:
    available: bool
    balance: Decimal
    equity: Decimal
    unrealized_pnl: Decimal
    position: PositionSnapshot | None


async def _account_snapshot(
    session: AsyncSession,
    environment: str,
    symbol: str,
) -> _AccountSnapshot:
    credentials = await cred_svc.get_decrypted(
        session,
        environment=environment,
        service="binance",
    )
    await session.rollback()
    if credentials is None:
        return _unavailable_account()

    api_key, api_secret = credentials
    try:
        async with BinanceClient(
            environment,
            api_key=api_key,
            api_secret=api_secret,
        ) as client:
            account = await BinanceExchange(client).get_account()
    except BinanceError:
        return _unavailable_account()

    position_out: PositionSnapshot | None = None
    position = next(
        (item for item in account.positions if item.symbol == symbol),
        None,
    )
    if position is not None and position.qty != 0:
        side = "LONG" if position.qty > 0 else "SHORT"
        leverage = (
            abs(position.qty) * position.entry_price / account.balance
            if account.balance > 0
            else Decimal("0")
        )
        position_out = PositionSnapshot(
            side=side,
            qty=str(abs(position.qty)),
            entry_price=_decimal(position.entry_price),
            mark_price=None,
            unrealized_pnl=_decimal(account.unrealized_pnl),
            leverage=f"{leverage:.2f}",
            has_price_stop=side == "LONG",
        )

    return _AccountSnapshot(
        available=True,
        balance=account.balance,
        equity=account.balance + account.unrealized_pnl,
        unrealized_pnl=account.unrealized_pnl,
        position=position_out,
    )


def _unavailable_account() -> _AccountSnapshot:
    return _AccountSnapshot(
        available=False,
        balance=Decimal("0"),
        equity=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position=None,
    )


async def _market_snapshot(
    environment: str,
    candles: list[Candle],
    market: MarketSpec,
) -> MarketSnapshot:
    mark_price: str | None = None
    change_pct: str | None = None
    observed_at: str | None = None
    reachable = False
    stale = True

    try:
        async with BinanceClient(environment) as client:
            mark, ticker = await asyncio.gather(
                client.get_mark_price(market.symbol),
                client.get_ticker_24h(market.symbol),
            )
        now = utc_now()
        observed = dt.datetime.fromtimestamp(mark.observed_at_ms / 1000, tz=dt.UTC)
        mark_price = str(mark.price)
        change_pct = str(ticker.price_change_percent)
        observed_at = observed.isoformat()
        reachable = True
        stale = (now - observed).total_seconds() > FRESH_FOR_SECONDS
    except BinanceError:
        pass
    now = utc_now()

    return MarketSnapshot(
        symbol=market.symbol,
        interval=market.interval,
        reachable=reachable,
        mark_price=mark_price,
        price_change_24h_pct=change_pct,
        observed_at=observed_at,
        stale=stale,
        next_close_utc=next_close_time(now, market.interval).isoformat(),
        seconds_to_next_close=round(seconds_until_next_close(now, market.interval), 1),
        sparkline=_sparkline(candles),
    )


async def _recent_candles(session: AsyncSession, market: MarketSpec) -> list[Candle]:
    rows = (
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
    return list(reversed(rows))


async def _breaker_snapshots(
    session: AsyncSession,
    now: dt.datetime,
    equity: Decimal,
    risk: RiskSpec,
) -> tuple[list[BreakerSnapshot], Decimal]:
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    output: list[BreakerSnapshot] = []
    month_realized = Decimal("0")
    available = equity > 0

    for book, sides, cap in (
        ("Long book", ("LONG",), risk.long_monthly_loss_cap),
        ("Short sleeve", ("SHORT",), risk.short_monthly_loss_cap),
    ):
        statement = select(func.coalesce(func.sum(Trade.realized_pnl), 0)).where(
            Trade.closed_at >= month_start, Trade.side.in_(sides)
        )
        pnl = Decimal(str((await session.execute(statement)).scalar_one()))
        month_realized += pnl
        state = evaluate_breaker(
            month_start_equity=equity if available else Decimal("1"),
            month_to_date_pnl=pnl,
            cap=cap,
        )
        output.append(
            BreakerSnapshot(
                book=book,
                month_to_date_pnl=_decimal(pnl),
                drawdown_pct=f"{state.drawdown_pct:.4f}",
                progress_pct=_breaker_progress(state.drawdown_pct),
                tripped=state.tripped if available else False,
                available=available,
            )
        )
    return output, month_realized


def _engine_snapshot(now: dt.datetime, gap_count: int) -> EngineSnapshot:
    heartbeat_at = ingest_service.worker_heartbeat_at
    heartbeat_age = ingest_service.worker_heartbeat_age(now)
    worker_running = ingest_service.is_running
    worker_healthy = (
        worker_running
        and heartbeat_age is not None
        and heartbeat_age <= WORKER_HEARTBEAT_SECONDS * 3
    )
    dead_man = ingest_service.dead_man
    return EngineSnapshot(
        worker_running=worker_running,
        worker_healthy=worker_healthy,
        heartbeat_at=heartbeat_at.isoformat() if heartbeat_at else None,
        heartbeat_age_seconds=round(heartbeat_age, 1) if heartbeat_age is not None else None,
        scheduler_alive=worker_running,
        database="ok",
        ingest_last_tick=dead_man.last_tick.isoformat() if dead_man.last_tick else None,
        ingest_overdue=dead_man.is_overdue(now),
        candle_gaps=gap_count,
    )


def _watch_snapshot(
    candles: list[Candle],
    mark_price: str | None,
    strategy: Strategy,
) -> StrategyWatchSnapshot:
    market = strategy.manifest.market
    strategy_candles = [
        StrategyCandle(
            open_time_ms=int(row.open_time.timestamp() * 1000),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
        )
        for row in candles
    ]
    watch = strategy.inspect(strategy_candles)
    if watch is None:
        return StrategyWatchSnapshot(
            available=False,
            last_closed_at=None,
            rules=[],
            disclaimer=(
                f"Waiting for {market.warmup_bars} closed {market.interval} "
                "candles required by this strategy. Thresholds shown after "
                "warm-up are descriptive and not a guaranteed trade or "
                "execution price."
            ),
        )

    mark = Decimal(mark_price) if mark_price is not None else None
    return StrategyWatchSnapshot(
        available=True,
        last_closed_at=(
            dt.datetime.fromtimestamp(watch.last_closed_open_time_ms / 1000, tz=dt.UTC)
            + dt.timedelta(seconds=INTERVAL_SECONDS[market.interval])
        ).isoformat(),
        rules=[_watch_rule(rule, mark) for rule in watch.rules],
        disclaimer=watch.disclaimer,
    )


def _watch_rule(
    rule: WatchRule,
    mark: Decimal | None,
) -> WatchRuleSnapshot:
    threshold = Decimal(str(rule.threshold)) if rule.threshold is not None else None
    distance = mark - threshold if mark is not None and threshold is not None else None
    distance_pct = (
        distance / threshold * Decimal("100")
        if distance is not None and threshold is not None and threshold != 0
        else None
    )
    return WatchRuleSnapshot(
        key=rule.key,
        label=rule.label,
        status=rule.status,
        tone=rule.tone,
        active=rule.active,
        condition=rule.condition,
        threshold_price=_decimal(threshold) if threshold is not None else None,
        distance=_decimal(distance) if distance is not None else None,
        distance_pct=_decimal(distance_pct) if distance_pct is not None else None,
    )


async def _activity_snapshots(
    session: AsyncSession,
    engine: EngineSnapshot,
    market: MarketSnapshot,
) -> list[ActivitySnapshot]:
    items: list[ActivitySnapshot] = []
    if engine.heartbeat_at is not None:
        items.append(
            ActivitySnapshot(
                ts=engine.heartbeat_at,
                label="Worker heartbeat observed",
                detail="Background ingest task and event loop are responsive",
                tone="ok" if engine.worker_healthy else "warn",
                badge="Live" if engine.worker_healthy else "Stale",
            )
        )
    if market.observed_at is not None and market.mark_price is not None:
        items.append(
            ActivitySnapshot(
                ts=market.observed_at,
                label="Market price refreshed",
                detail=f"{market.symbol} mark {market.mark_price}",
                tone="ok" if not market.stale else "warn",
                badge="Live" if not market.stale else "Stale",
            )
        )

    events = (
        (
            await session.execute(
                select(Event)
                .where(Event.category != "security")
                .order_by(Event.ts.desc())
                .limit(RECENT_EVENTS)
            )
        )
        .scalars()
        .all()
    )
    for event in events:
        tone = "err" if event.level == "ERROR" else "warn" if event.level == "WARN" else "neutral"
        items.append(
            ActivitySnapshot(
                ts=event.ts.isoformat(),
                label=event.message,
                detail=f"{event.category} event",
                tone=tone,
                badge=event.level.title(),
            )
        )
    return sorted(items, key=lambda item: item.ts, reverse=True)[:5]


async def _briefing_snapshot(session: AsyncSession) -> BriefingSnapshot:
    row = (
        await session.execute(select(Briefing).order_by(Briefing.briefing_date.desc()).limit(1))
    ).scalar_one_or_none()
    isolation = "Read-only human context; never a trading input."
    if row is None:
        return BriefingSnapshot(
            available=False,
            sentiment=None,
            generated_at=None,
            bullets=[],
            isolation_notice=isolation,
        )

    bullets: list[BriefingBulletSnapshot] = []
    for item in row.bullets[:3]:
        if isinstance(item, dict):
            text = item.get("text")
            source = item.get("source")
            if isinstance(text, str):
                bullets.append(
                    BriefingBulletSnapshot(
                        text=text,
                        source=source if isinstance(source, str) else "",
                    )
                )
    return BriefingSnapshot(
        available=bool(bullets),
        sentiment=row.sentiment,
        generated_at=row.generated_at.isoformat(),
        bullets=bullets,
        isolation_notice=isolation,
    )


def _decimal(value: Decimal) -> str:
    return format(value.quantize(PRICE_PLACES), "f")


def _breaker_progress(drawdown_pct: Decimal) -> str:
    """Return a bounded display-only percentage of the independent 4% breaker."""
    progress = min(
        Decimal("100"),
        abs(drawdown_pct) / Decimal("0.04") * Decimal("100"),
    )
    return f"{progress:.2f}"


def _sparkline(candles: list[Candle]) -> list[SparkPoint]:
    """Normalize chart geometry server-side without converting money to float."""
    rows = candles[-SPARKLINE_POINTS:]
    if not rows:
        return []
    baseline = rows[0].close
    return [
        SparkPoint(
            ts=row.open_time.isoformat(),
            close=str(row.close),
            normalized_bps=(
                int(((row.close / baseline) - Decimal("1")) * Decimal("10000"))
                if baseline != 0
                else 0
            ),
        )
        for row in rows
    ]
