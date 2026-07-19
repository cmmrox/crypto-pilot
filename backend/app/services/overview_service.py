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

from app.bot.ingest import (
    INTERVAL,
    SYMBOL,
    WORKER_HEARTBEAT_SECONDS,
    ingest_service,
)
from app.bot.scheduler import next_close_time, seconds_until_next_close, utc_now
from app.bot.service import bot_service
from app.db.models import Briefing, Candle, Event, Trade
from app.execution import candles as candle_svc
from app.execution.binance_client import BinanceClient, BinanceError
from app.execution.binance_exchange import BinanceExchange
from app.risk.breakers import evaluate_breaker
from app.services import credentials as cred_svc
from app.services.settings_store import get_settings_row
from app.strategies.base import Candle as StrategyCandle
from app.strategies.watch import StrategyWatch, inspect_strategy_watch

FRESH_FOR_SECONDS = 10
SPARKLINE_POINTS = 24
WATCH_CANDLES = 400
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
    close: str | None
    ema20: str | None
    ema50: str | None
    ema200: str | None
    sma200: str | None
    atr14: str | None
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
    strategy = settings_row.active_strategy
    bot = await bot_service.status(session)
    candles = await _recent_candles(session)
    gaps = await candle_svc.detect_gaps(session, SYMBOL, INTERVAL)
    gap_count = len(gaps)
    for candle in candles:
        session.expunge(candle)
    await session.rollback()
    market, account = await asyncio.gather(
        _market_snapshot(environment, candles),
        _account_snapshot(session, environment),
    )
    if account.position is not None:
        account = replace(
            account,
            position=replace(account.position, mark_price=market.mark_price),
        )
    now = utc_now()
    breakers, month_realized = await _breaker_snapshots(session, now, account.equity)
    watch = _watch_snapshot(candles, market.mark_price)
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
        (item for item in account.positions if item.symbol == SYMBOL),
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


async def _market_snapshot(environment: str, candles: list[Candle]) -> MarketSnapshot:
    mark_price: str | None = None
    change_pct: str | None = None
    observed_at: str | None = None
    reachable = False
    stale = True

    try:
        async with BinanceClient(environment) as client:
            mark, ticker = await asyncio.gather(
                client.get_mark_price(SYMBOL),
                client.get_ticker_24h(SYMBOL),
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
        symbol=SYMBOL,
        interval=INTERVAL,
        reachable=reachable,
        mark_price=mark_price,
        price_change_24h_pct=change_pct,
        observed_at=observed_at,
        stale=stale,
        next_close_utc=next_close_time(now, INTERVAL).isoformat(),
        seconds_to_next_close=round(seconds_until_next_close(now, INTERVAL), 1),
        sparkline=_sparkline(candles),
    )


async def _recent_candles(session: AsyncSession) -> list[Candle]:
    rows = (
        (
            await session.execute(
                select(Candle)
                .where(Candle.symbol == SYMBOL, Candle.interval == INTERVAL)
                .order_by(Candle.open_time.desc())
                .limit(WATCH_CANDLES)
            )
        )
        .scalars()
        .all()
    )
    return list(reversed(rows))


async def _breaker_snapshots(
    session: AsyncSession, now: dt.datetime, equity: Decimal
) -> tuple[list[BreakerSnapshot], Decimal]:
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    output: list[BreakerSnapshot] = []
    month_realized = Decimal("0")
    available = equity > 0

    for book, sides in (("Long book", ("LONG",)), ("Short sleeve", ("SHORT",))):
        statement = select(func.coalesce(func.sum(Trade.realized_pnl), 0)).where(
            Trade.closed_at >= month_start, Trade.side.in_(sides)
        )
        pnl = Decimal(str((await session.execute(statement)).scalar_one()))
        month_realized += pnl
        state = evaluate_breaker(
            month_start_equity=equity if available else Decimal("1"),
            month_to_date_pnl=pnl,
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


def _watch_snapshot(candles: list[Candle], mark_price: str | None) -> StrategyWatchSnapshot:
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
    watch = inspect_strategy_watch(strategy_candles)
    disclaimer = (
        "Thresholds are evaluated on a closed 4h candle; they are not a "
        "guaranteed trade or execution price."
    )
    if watch is None:
        return StrategyWatchSnapshot(
            available=False,
            last_closed_at=None,
            close=None,
            ema20=None,
            ema50=None,
            ema200=None,
            sma200=None,
            atr14=None,
            rules=[],
            disclaimer=disclaimer,
        )

    mark = Decimal(mark_price) if mark_price is not None else None
    return StrategyWatchSnapshot(
        available=True,
        last_closed_at=(
            dt.datetime.fromtimestamp(watch.last_closed_open_time_ms / 1000, tz=dt.UTC)
            + dt.timedelta(hours=4)
        ).isoformat(),
        close=_price(watch.close),
        ema20=_price(watch.ema20),
        ema50=_price(watch.ema50),
        ema200=_price(watch.ema200),
        sma200=_price(watch.sma200),
        atr14=_price(watch.atr14),
        rules=_watch_rules(watch, mark),
        disclaimer=disclaimer,
    )


def _watch_rules(watch: StrategyWatch, mark: Decimal | None) -> list[WatchRuleSnapshot]:
    long_status = "Active" if watch.long_regime else "Waiting"
    pullback_status = (
        "Ready at last close"
        if watch.pullback_resume
        else "Monitoring"
        if watch.long_regime
        else "Waiting"
    )
    short_status = "Active" if watch.deep_bear else "Not active"
    return [
        _watch_rule(
            key="long_regime",
            label="Long regime",
            status=long_status,
            tone="ok" if watch.long_regime else "neutral",
            active=watch.long_regime,
            condition="Close > SMA200 and EMA50 > EMA200",
            threshold=watch.sma200,
            mark=mark,
        ),
        _watch_rule(
            key="pullback_resume",
            label="Pullback resume",
            status=pullback_status,
            tone="ok" if watch.pullback_resume else "warn",
            active=watch.pullback_resume,
            condition="A closed 4h candle reclaims EMA20 after a bull-regime pullback",
            threshold=watch.ema20,
            mark=mark,
        ),
        _watch_rule(
            key="deep_bear_short",
            label="Deep-bear short",
            status=short_status,
            tone="err" if watch.deep_bear else "neutral",
            active=watch.deep_bear,
            condition="Close < SMA200, EMA50 < EMA200, and close < SMA200 - 0.5 ATR",
            threshold=watch.deep_bear_threshold,
            mark=mark,
        ),
    ]


def _watch_rule(
    *,
    key: str,
    label: str,
    status: str,
    tone: str,
    active: bool,
    condition: str,
    threshold: float,
    mark: Decimal | None,
) -> WatchRuleSnapshot:
    threshold_decimal = Decimal(str(threshold))
    distance = mark - threshold_decimal if mark is not None else None
    distance_pct = (
        distance / threshold_decimal * Decimal("100")
        if distance is not None and threshold_decimal != 0
        else None
    )
    return WatchRuleSnapshot(
        key=key,
        label=label,
        status=status,
        tone=tone,
        active=active,
        condition=condition,
        threshold_price=_decimal(threshold_decimal),
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
                detail=f"{SYMBOL} mark {market.mark_price}",
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


def _price(value: float) -> str:
    return _decimal(Decimal(str(value)))


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
