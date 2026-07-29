"""Chronological Trend Rider v6 replay using production strategy and risk code."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Literal, cast

import numpy as np
import pandas as pd
from app.execution.filters import SymbolFilters, clamp_qty
from app.risk.sizing import size_long, size_short
from app.strategies import (
    EnterLong,
    EnterShort,
    ExitAll,
    MoveStop,
    ResizeShort,
    TradeState,
    default_strategy,
    engine,
    get_strategy,
)
from app.strategies.base import Candle as StrategyCandle

ZERO = Decimal("0")
ONE = Decimal("1")
DEFAULT_MANIFEST = default_strategy().manifest


@dataclass(frozen=True)
class ReplayConfig:
    initial_capital: Decimal = Decimal("100")
    risk_pct: Decimal = DEFAULT_MANIFEST.risk.long_risk_pct
    leverage_cap: Decimal = DEFAULT_MANIFEST.risk.leverage_cap
    long_fee_rate: Decimal = Decimal(str(engine.FEE))
    short_cost_rate: Decimal = Decimal(str(engine.COST))
    funding_enabled: bool = True
    long_breaker_cap: Decimal = DEFAULT_MANIFEST.risk.long_monthly_loss_cap
    short_breaker_cap: Decimal = DEFAULT_MANIFEST.risk.short_monthly_loss_cap
    resize_drift: Decimal = DEFAULT_MANIFEST.risk.short_resize_drift
    symbol: str = DEFAULT_MANIFEST.market.symbol


@dataclass
class Position:
    side: Literal["LONG", "SHORT"]
    qty: Decimal
    entry_price: Decimal
    opened_at: pd.Timestamp
    entry_equity: Decimal
    entry_fee: Decimal
    stop: Decimal | None = None
    tp1: Decimal | None = None
    tp1_done: bool = False
    highest: Decimal | None = None
    realized_partial: Decimal = ZERO
    fees: Decimal = ZERO
    funding: Decimal = ZERO


@dataclass(frozen=True)
class ReplayResult:
    config: ReplayConfig
    start: pd.Timestamp
    end: pd.Timestamp
    latest_close: Decimal
    final_equity: Decimal
    profit: Decimal
    total_return: Decimal
    max_drawdown: Decimal
    cagr: Decimal
    sharpe: Decimal
    trades: pd.DataFrame
    equity: pd.DataFrame
    monthly: pd.DataFrame
    open_position: dict[str, str] | None
    skipped_long_entries: int
    skipped_short_entries: int
    long_breaker_trips: int
    short_breaker_trips: int
    funding_events_applied: int
    funding_mark_fallbacks: int
    period_bars: int


class ReferenceReplayEngine:
    """Independent reference replay on closed 4h OHLC bars.

    The strategy math/constants and risk sizing/filter behavior are imported
    from production. It remains separate from the plugin only to detect adapter
    divergence; normal backtests use ``PluginReplayEngine`` below.
    """

    def __init__(
        self,
        candles: pd.DataFrame,
        funding: pd.DataFrame,
        filters: SymbolFilters,
        config: ReplayConfig,
        *,
        start: pd.Timestamp,
    ) -> None:
        if config.initial_capital <= 0:
            raise ValueError("initial capital must be positive")
        frame = candles.copy()
        frame["dt"] = pd.to_datetime(frame["dt"], utc=True)
        frame = frame.sort_values("dt").reset_index(drop=True)
        if frame["dt"].duplicated().any():
            raise ValueError("duplicate candle timestamps are not allowed")
        steps = frame["dt"].diff().dropna()
        if not bool((steps == pd.Timedelta(hours=4)).all()):
            raise ValueError("candle data must be a continuous 4h series")
        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        self.df = engine.add_indicators(frame)
        self.deep_bear = engine.short_target(self.df) < 0
        self.vol_scale = self._vol_scale(self.df)
        self.funding = funding.copy()
        if not self.funding.empty:
            self.funding["dt"] = pd.to_datetime(self.funding["dt"], utc=True, format="mixed")
            self.funding["bar_open"] = self.funding["dt"].dt.floor("4h")
            self.funding["funding_rate"] = self.funding["funding_rate"].map(
                lambda value: Decimal(str(value))
            )
            self.funding["mark_price"] = self.funding["mark_price"].map(
                lambda value: Decimal(str(value))
            )
        self.filters = filters
        self.config = config
        self.start = pd.Timestamp(start).tz_convert("UTC")

        starts = self.df.index[self.df["dt"] >= self.start]
        if len(starts) == 0:
            raise ValueError("start is after available candles")
        self.start_i = int(starts[0])
        if self.start_i < 200:
            raise ValueError("at least 200 warmup candles are required before start")

        self.cash = config.initial_capital
        self.position: Position | None = None
        self.halted_long = False
        self.halted_short = False
        self.month: tuple[int, int] | None = None
        self.month_start_equity = config.initial_capital
        self.long_month_delta = ZERO
        self.short_month_delta = ZERO
        self.previous_equity = config.initial_capital
        self.was_below = self._warmup_was_below(self.start_i - 1)
        self.reg_prev = bool(self.df.iloc[self.start_i - 2]["regime"])
        self.trades: list[dict[str, object]] = []
        self.equity_rows: list[dict[str, object]] = []
        self.skipped_long_entries = 0
        self.skipped_short_entries = 0
        self.long_breaker_trips = 0
        self.short_breaker_trips = 0
        self.funding_events_applied = 0
        self.funding_mark_fallbacks = 0

    @staticmethod
    def _vol_scale(df: pd.DataFrame) -> pd.Series[Any]:
        ret = df["close"].pct_change().fillna(0.0)
        rv = ret.ewm(span=engine.SLEEVE_VOL_SPAN, adjust=False).std() * np.sqrt(
            engine.BARS_PER_YEAR
        )
        return cast(
            "pd.Series[Any]",
            (engine.SLEEVE_VOL_TARGET / rv).clip(upper=1.0).fillna(0.0),
        )

    def _warmup_was_below(self, prev_i: int) -> bool:
        for index in range(prev_i, 0, -1):
            row = self.df.iloc[index]
            if not bool(row["regime"]):
                break
            if float(row["close"]) < float(row["ema20"]):
                return True
        return False

    def run(self) -> ReplayResult:
        for i in range(self.start_i, len(self.df)):
            row = self.df.iloc[i]
            prev = self.df.iloc[i - 1]
            dt_value = pd.Timestamp(row["dt"])
            open_price = Decimal(str(row["open"]))
            bar_side = self.position.side if self.position is not None else None
            self._roll_month(dt_value, open_price)
            self._apply_funding_at_open(dt_value, open_price)
            self._process_open(i, row, prev)
            if bar_side is None and self.position is not None:
                bar_side = self.position.side
            self._process_intrabar(i, row)
            close = Decimal(str(row["close"]))
            current_equity = self._mark_equity(close)
            self._update_breakers(current_equity, bar_side)
            self._record_equity(dt_value, close, current_equity)
            self._update_signal_memory(row, prev)
            self.previous_equity = current_equity

        if not self.equity_rows:
            raise RuntimeError("replay produced no equity rows")
        equity_frame = pd.DataFrame(self.equity_rows)
        trades_frame = pd.DataFrame(self.trades)
        monthly = _monthly_returns(equity_frame)
        final_equity = Decimal(str(equity_frame.iloc[-1]["equity"]))
        total_return = (final_equity / self.config.initial_capital) - ONE
        max_drawdown = _max_drawdown(equity_frame)
        start_dt = pd.Timestamp(equity_frame.iloc[0]["dt"])
        end_dt = pd.Timestamp(equity_frame.iloc[-1]["dt"])
        years = Decimal(str((end_dt - start_dt).total_seconds() / (365.2425 * 86400)))
        cagr = (
            Decimal(str(float(final_equity / self.config.initial_capital) ** (1 / float(years))))
            - ONE
            if years > 0 and final_equity > 0
            else Decimal("-1")
        )
        sharpe = _sharpe(equity_frame)
        open_position = None
        if self.position is not None:
            open_position = {
                "side": self.position.side,
                "qty": str(self.position.qty),
                "entry_price": str(self.position.entry_price),
                "opened_at": self.position.opened_at.isoformat(),
            }
        return ReplayResult(
            config=self.config,
            start=start_dt,
            end=end_dt,
            latest_close=Decimal(str(self.df.iloc[-1]["close"])),
            final_equity=final_equity,
            profit=final_equity - self.config.initial_capital,
            total_return=total_return,
            max_drawdown=max_drawdown,
            cagr=cagr,
            sharpe=sharpe,
            trades=trades_frame,
            equity=equity_frame,
            monthly=monthly,
            open_position=open_position,
            skipped_long_entries=self.skipped_long_entries,
            skipped_short_entries=self.skipped_short_entries,
            long_breaker_trips=self.long_breaker_trips,
            short_breaker_trips=self.short_breaker_trips,
            funding_events_applied=self.funding_events_applied,
            funding_mark_fallbacks=self.funding_mark_fallbacks,
            period_bars=len(equity_frame),
        )

    def _roll_month(self, timestamp: pd.Timestamp, open_price: Decimal) -> None:
        current = (timestamp.year, timestamp.month)
        if current == self.month:
            return
        self.month = current
        self.halted_long = False
        self.halted_short = False
        self.long_month_delta = ZERO
        self.short_month_delta = ZERO
        self.month_start_equity = self._mark_equity(open_price)
        self.previous_equity = self.month_start_equity

    def _apply_funding_at_open(self, timestamp: pd.Timestamp, fallback_price: Decimal) -> None:
        if not self.config.funding_enabled or self.position is None or self.funding.empty:
            return
        rows = self.funding[self.funding["bar_open"] == timestamp]
        for _, funding_row in rows.iterrows():
            rate = funding_row["funding_rate"]
            mark = funding_row["mark_price"]
            if not mark.is_finite() or mark <= 0:
                mark = fallback_price
                self.funding_mark_fallbacks += 1
            notional = self.position.qty * mark
            payment = -notional * rate if self.position.side == "LONG" else notional * rate
            self.cash += payment
            self.position.funding += payment
            self.funding_events_applied += 1

    def _process_open(self, i: int, row: pd.Series[Any], prev: pd.Series[Any]) -> None:
        open_price = Decimal(str(row["open"]))
        if self.position is not None:
            if self.position.side == "LONG":
                if self.halted_long or not bool(prev["regime"]):
                    reason = "monthly_breaker" if self.halted_long else "regime_off"
                    self._close_position(open_price, pd.Timestamp(row["dt"]), reason)
            elif self.halted_short or not bool(self.deep_bear.iloc[i - 1]):
                reason = "monthly_breaker" if self.halted_short else "deep_bear_ended"
                self._close_position(open_price, pd.Timestamp(row["dt"]), reason)
            else:
                self._resize_short(i, open_price, pd.Timestamp(row["dt"]))

        if self.position is not None:
            return
        if bool(prev["regime"]) and not self.halted_long and not pd.isna(prev["sma200"]):
            fresh = not self.reg_prev
            resume = self.was_below and float(prev["close"]) > float(prev["ema20"])
            if fresh or resume:
                self._open_long(open_price, Decimal(str(prev["atr"])), pd.Timestamp(row["dt"]))
                self.was_below = False
                return
        if bool(self.deep_bear.iloc[i - 1]) and not self.halted_short:
            self._open_short(i, open_price, pd.Timestamp(row["dt"]))

    def _open_long(self, price: Decimal, atr: Decimal, timestamp: pd.Timestamp) -> None:
        equity = self._mark_equity(price)
        stop_distance = Decimal(str(engine.STOP_ATR)) * atr
        sizing = size_long(
            equity=equity,
            risk_pct=self.config.risk_pct,
            stop_distance=stop_distance,
            price=price,
            leverage_cap=self.config.leverage_cap,
            filters=self.filters,
        )
        if not sizing.ok:
            self.skipped_long_entries += 1
            return
        fee = sizing.qty * price * self.config.long_fee_rate
        self.cash -= fee
        self.position = Position(
            side="LONG",
            qty=sizing.qty,
            entry_price=price,
            opened_at=timestamp,
            entry_equity=equity,
            entry_fee=fee,
            stop=price - stop_distance,
            tp1=price + Decimal(str(engine.TP1_R)) * stop_distance,
            highest=price,
            fees=fee,
        )

    def _open_short(self, i: int, price: Decimal, timestamp: pd.Timestamp) -> None:
        equity = self._mark_equity(price)
        realized_vol = self._realized_vol(i - 1)
        sizing = size_short(
            equity=equity,
            weight_pct=Decimal(str(engine.SLEEVE_WEIGHT * 100)),
            vol_target=Decimal(str(engine.SLEEVE_VOL_TARGET)),
            realized_vol=realized_vol,
            price=price,
            leverage_cap=self.config.leverage_cap,
            filters=self.filters,
        )
        if not sizing.ok:
            self.skipped_short_entries += 1
            return
        fee = sizing.qty * price * self.config.short_cost_rate
        self.cash -= fee
        self.position = Position(
            side="SHORT",
            qty=sizing.qty,
            entry_price=price,
            opened_at=timestamp,
            entry_equity=equity,
            entry_fee=fee,
            fees=fee,
        )

    def _resize_short(self, i: int, price: Decimal, timestamp: pd.Timestamp) -> None:
        if self.position is None or self.position.side != "SHORT":
            return
        equity = self._mark_equity(price)
        realized_vol = self._realized_vol(i - 1)
        sizing = size_short(
            equity=equity,
            weight_pct=Decimal(str(engine.SLEEVE_WEIGHT * 100)),
            vol_target=Decimal(str(engine.SLEEVE_VOL_TARGET)),
            realized_vol=realized_vol,
            price=price,
            leverage_cap=self.config.leverage_cap,
            filters=self.filters,
        )
        if not sizing.ok:
            return
        current_notional = self.position.qty * price
        if current_notional <= 0:
            return
        drift = abs(sizing.notional - current_notional) / current_notional
        if drift <= self.config.resize_drift:
            return
        delta_qty = sizing.qty - self.position.qty
        if delta_qty == 0:
            return
        fee = abs(delta_qty) * price * self.config.short_cost_rate
        realized = ZERO
        if delta_qty < 0:
            reduce_qty = abs(delta_qty)
            realized = (self.position.entry_price - price) * reduce_qty
            self.cash += realized
            self.position.realized_partial += realized
        else:
            old_notional = self.position.qty * self.position.entry_price
            added_notional = delta_qty * price
            self.position.entry_price = (old_notional + added_notional) / sizing.qty
        self.cash -= fee
        self.position.fees += fee
        self.position.qty = sizing.qty
        del timestamp

    def _realized_vol(self, index: int) -> Decimal:
        scale = Decimal(str(float(self.vol_scale.iloc[index])))
        if scale <= 0:
            return ZERO
        return Decimal(str(engine.SLEEVE_VOL_TARGET)) / scale

    def _process_intrabar(self, i: int, row: pd.Series[Any]) -> None:
        if self.position is None or self.position.side != "LONG":
            return
        position = self.position
        open_price = Decimal(str(row["open"]))
        high = Decimal(str(row["high"]))
        low = Decimal(str(row["low"]))
        atr = Decimal(str(row["atr"]))
        timestamp = pd.Timestamp(row["dt"])
        if position.stop is not None and low <= position.stop:
            fill = open_price if open_price < position.stop else position.stop
            self._close_position(fill, timestamp, "stop")
            return
        if not position.tp1_done and position.tp1 is not None and high >= position.tp1:
            fill = open_price if open_price > position.tp1 else position.tp1
            tp_qty = _production_tp_qty(position.qty, Decimal(str(engine.TP1_FRAC)), self.filters)
            if tp_qty > 0:
                realized = (fill - position.entry_price) * tp_qty
                fee = fill * tp_qty * self.config.long_fee_rate
                self.cash += realized - fee
                position.realized_partial += realized
                position.fees += fee
                position.qty -= tp_qty
                position.tp1_done = True
                position.stop = position.entry_price
        if self.position is None:
            return
        position.highest = max(position.highest or high, high)
        if position.tp1_done and position.stop is not None:
            trail = position.highest - Decimal(str(engine.TRAIL_ATR)) * atr
            position.stop = max(position.stop, trail)
        del i

    def _close_position(self, price: Decimal, timestamp: pd.Timestamp, reason: str) -> None:
        position = self.position
        if position is None:
            return
        if position.side == "LONG":
            realized = (price - position.entry_price) * position.qty
            rate = self.config.long_fee_rate
        else:
            realized = (position.entry_price - price) * position.qty
            rate = self.config.short_cost_rate
        fee = price * position.qty * rate
        self.cash += realized - fee
        position.fees += fee
        total_realized = position.realized_partial + realized
        net = total_realized + position.funding - position.fees
        self.trades.append(
            {
                "side": position.side,
                "opened_at": position.opened_at,
                "closed_at": timestamp,
                "entry_price": str(position.entry_price),
                "exit_price": str(price),
                "initial_equity": str(position.entry_equity),
                "gross_pnl": str(total_realized),
                "fees": str(position.fees),
                "funding": str(position.funding),
                "net_pnl": str(net),
                "return_on_entry_equity": str(net / position.entry_equity),
                "exit_reason": reason,
            }
        )
        self.position = None

    def _mark_equity(self, price: Decimal) -> Decimal:
        if self.position is None:
            return self.cash
        if self.position.side == "LONG":
            unrealized = (price - self.position.entry_price) * self.position.qty
        else:
            unrealized = (self.position.entry_price - price) * self.position.qty
        return self.cash + unrealized

    def _update_breakers(
        self, current_equity: Decimal, bar_side: Literal["LONG", "SHORT"] | None
    ) -> None:
        delta = current_equity - self.previous_equity
        if bar_side == "LONG":
            self.long_month_delta += delta
        elif bar_side == "SHORT":
            self.short_month_delta += delta
        long_threshold = -(self.month_start_equity * self.config.long_breaker_cap)
        short_threshold = -(self.month_start_equity * self.config.short_breaker_cap)
        if not self.halted_long and self.long_month_delta < long_threshold:
            self.halted_long = True
            self.long_breaker_trips += 1
        if not self.halted_short and self.short_month_delta < short_threshold:
            self.halted_short = True
            self.short_breaker_trips += 1

    def _record_equity(
        self, timestamp: pd.Timestamp, close: Decimal, current_equity: Decimal
    ) -> None:
        self.equity_rows.append(
            {
                "dt": timestamp,
                "close": str(close),
                "equity": str(current_equity),
                "cash": str(self.cash),
                "position": self.position.side if self.position is not None else "FLAT",
                "qty": str(self.position.qty) if self.position is not None else "0",
                "halted_long": self.halted_long,
                "halted_short": self.halted_short,
            }
        )

    def _update_signal_memory(self, row: pd.Series[Any], prev: pd.Series[Any]) -> None:
        if float(row["close"]) < float(row["ema20"]):
            self.was_below = True
        elif self.position is not None and self.position.side == "LONG":
            self.was_below = False
        self.reg_prev = bool(prev["regime"])


class PluginReplayEngine(ReferenceReplayEngine):
    """Replay the live ``on_candle`` adapter with the same OHLC account model.

    This is the deterministic bridge between Stage 3's vectorized parity engine
    and the BotService intent dispatcher.  Signals are produced at one candle
    close and applied at the next candle open, just like the deployed scheduler.
    """

    def __init__(
        self,
        candles: pd.DataFrame,
        funding: pd.DataFrame,
        filters: SymbolFilters,
        config: ReplayConfig,
        *,
        start: pd.Timestamp,
    ) -> None:
        super().__init__(candles, funding, filters, config, start=start)
        self.strategy = get_strategy(DEFAULT_MANIFEST.strategy_id)
        self.intent_trace: list[dict[str, object]] = []
        self._all_strategy_candles = [
            StrategyCandle(
                open_time_ms=int(timestamp.timestamp() * 1000),
                open=float(open_price),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=float(volume),
            )
            for timestamp, open_price, high, low, close, volume in zip(
                pd.to_datetime(self.df["dt"], utc=True),
                self.df["open"],
                self.df["high"],
                self.df["low"],
                self.df["close"],
                self.df["volume"],
                strict=True,
            )
        ]

    def _process_open(self, i: int, row: pd.Series[Any], prev: pd.Series[Any]) -> None:
        open_price = Decimal(str(row["open"]))
        timestamp = pd.Timestamp(row["dt"])
        if self.position is not None and (
            (self.position.side == "LONG" and self.halted_long)
            or (self.position.side == "SHORT" and self.halted_short)
        ):
            self._close_position(open_price, timestamp, "monthly_breaker")

        state = self._plugin_state(i, prev)
        intents = self.strategy.on_candle(
            self._strategy_candles(i),
            state,
        )
        self.intent_trace.append(
            {
                "dt": timestamp,
                "intents": [type(intent).__name__ for intent in intents],
            }
        )
        for intent in intents:
            if isinstance(intent, ExitAll) and self.position is not None:
                self._close_position(open_price, timestamp, _exit_reason(intent))
            elif (
                isinstance(intent, MoveStop)
                and self.position is not None
                and self.position.side == "LONG"
                and self.position.stop is not None
            ):
                self.position.stop = max(self.position.stop, Decimal(str(intent.price)))
            elif (
                isinstance(intent, ResizeShort)
                and self.position is not None
                and self.position.side == "SHORT"
            ):
                self._resize_short_from_weight(Decimal(str(intent.target_weight)), open_price)
            elif isinstance(intent, EnterLong) and self.position is None and not self.halted_long:
                self._open_long_from_intent(intent, open_price, timestamp)
            elif isinstance(intent, EnterShort) and self.position is None and not self.halted_short:
                self._open_short_from_weight(Decimal(str(intent.weight)), open_price, timestamp)

    def _plugin_state(self, i: int, prev: pd.Series[Any]) -> TradeState:
        position = self.position
        short_weight = 0.0
        if position is not None and position.side == "SHORT" and self.previous_equity > 0:
            short_weight = float(position.qty * Decimal(str(prev["close"])) / self.previous_equity)
        return TradeState(
            equity=float(self.previous_equity),
            long_position=position is not None and position.side == "LONG",
            short_weight=short_weight,
            long_entry=(
                float(position.entry_price)
                if position is not None and position.side == "LONG"
                else None
            ),
            long_stop=(
                float(position.stop)
                if position is not None and position.side == "LONG" and position.stop is not None
                else None
            ),
            highest_high=(
                float(position.highest)
                if position is not None and position.side == "LONG" and position.highest is not None
                else None
            ),
            tp1_done=(
                position.tp1_done if position is not None and position.side == "LONG" else False
            ),
            last_long_closed_at_ms=self._last_long_closed_at_ms(),
            halted_long=self.halted_long,
            halted_short=self.halted_short,
        )

    def _last_long_closed_at_ms(self) -> int | None:
        for trade in reversed(self.trades):
            if trade["side"] == "LONG":
                return int(pd.Timestamp(trade["closed_at"]).timestamp() * 1000)
        return None

    def _strategy_candles(self, current_i: int) -> list[StrategyCandle]:
        return self._all_strategy_candles[:current_i]

    def _open_long_from_intent(
        self, intent: EnterLong, price: Decimal, timestamp: pd.Timestamp
    ) -> None:
        equity = self._mark_equity(price)
        stop_distance = Decimal(str(intent.stop_distance))
        sizing = size_long(
            equity=equity,
            risk_pct=self.config.risk_pct,
            stop_distance=stop_distance,
            price=price,
            leverage_cap=self.config.leverage_cap,
            filters=self.filters,
        )
        if not sizing.ok:
            self.skipped_long_entries += 1
            return
        fee = sizing.qty * price * self.config.long_fee_rate
        self.cash -= fee
        tp_r, _tp_fraction = intent.tp_levels[0]
        self.position = Position(
            side="LONG",
            qty=sizing.qty,
            entry_price=price,
            opened_at=timestamp,
            entry_equity=equity,
            entry_fee=fee,
            stop=price - stop_distance,
            tp1=price + Decimal(str(tp_r)) * stop_distance,
            highest=price,
            fees=fee,
        )

    def _open_short_from_weight(
        self, weight: Decimal, price: Decimal, timestamp: pd.Timestamp
    ) -> None:
        equity = self._mark_equity(price)
        qty = clamp_qty(equity * weight / price, self.filters)
        if qty <= 0 or qty * price < self.filters.min_notional:
            self.skipped_short_entries += 1
            return
        fee = qty * price * self.config.short_cost_rate
        self.cash -= fee
        self.position = Position(
            side="SHORT",
            qty=qty,
            entry_price=price,
            opened_at=timestamp,
            entry_equity=equity,
            entry_fee=fee,
            fees=fee,
        )

    def _resize_short_from_weight(self, weight: Decimal, price: Decimal) -> None:
        position = self.position
        if position is None or position.side != "SHORT":
            return
        equity = self._mark_equity(price)
        target_qty = clamp_qty(equity * weight / price, self.filters)
        if target_qty <= 0 or target_qty * price < self.filters.min_notional:
            return
        current_notional = position.qty * price
        target_notional = target_qty * price
        if current_notional <= 0:
            return
        drift = abs(target_notional - current_notional) / current_notional
        if drift <= self.config.resize_drift:
            return
        delta_qty = target_qty - position.qty
        if delta_qty == 0:
            return
        fee = abs(delta_qty) * price * self.config.short_cost_rate
        if delta_qty < 0:
            realized = (position.entry_price - price) * abs(delta_qty)
            self.cash += realized
            position.realized_partial += realized
        else:
            old_notional = position.qty * position.entry_price
            position.entry_price = (old_notional + delta_qty * price) / target_qty
        self.cash -= fee
        position.fees += fee
        position.qty = target_qty

    def _process_intrabar(self, i: int, row: pd.Series[Any]) -> None:
        del i
        position = self.position
        if position is None or position.side != "LONG":
            return
        open_price = Decimal(str(row["open"]))
        high = Decimal(str(row["high"]))
        low = Decimal(str(row["low"]))
        timestamp = pd.Timestamp(row["dt"])
        if position.stop is not None and low <= position.stop:
            fill = open_price if open_price < position.stop else position.stop
            self._close_position(fill, timestamp, "stop")
            return
        if not position.tp1_done and position.tp1 is not None and high >= position.tp1:
            fill = open_price if open_price > position.tp1 else position.tp1
            tp_qty = _production_tp_qty(position.qty, Decimal(str(engine.TP1_FRAC)), self.filters)
            if tp_qty > 0:
                realized = (fill - position.entry_price) * tp_qty
                fee = fill * tp_qty * self.config.long_fee_rate
                self.cash += realized - fee
                position.realized_partial += realized
                position.fees += fee
                position.qty -= tp_qty
                position.tp1_done = True
        position.highest = max(position.highest or high, high)


def _exit_reason(intent: ExitAll) -> str:
    if intent.reason == "regime off":
        return "regime_off"
    if intent.reason == "deep-bear ended":
        return "deep_bear_ended"
    return intent.reason


def _production_tp_qty(qty: Decimal, fraction: Decimal, filters: SymbolFilters) -> Decimal:
    """Mirror OrderManager precision rounding, then keep the order exchange-valid."""
    exponent = qty.as_tuple().exponent
    raw = qty * fraction
    if isinstance(exponent, int) and exponent < 0:
        raw = raw.quantize(Decimal(1).scaleb(exponent))
    return min(qty, clamp_qty(raw, filters))


def _monthly_returns(equity: pd.DataFrame) -> pd.DataFrame:
    frame = equity.copy()
    frame["dt"] = pd.to_datetime(frame["dt"], utc=True)
    frame["equity_num"] = frame["equity"].map(float)
    monthly = frame.set_index("dt")["equity_num"].resample("ME").last().pct_change()
    if not monthly.empty:
        first = frame["equity_num"].iloc[0]
        monthly.iloc[0] = (
            frame.set_index("dt")["equity_num"].resample("ME").last().iloc[0] / first
        ) - 1
    return monthly.rename("return").reset_index()


def _max_drawdown(equity: pd.DataFrame) -> Decimal:
    values = equity["equity"].map(float)
    peaks = values.cummax()
    drawdown = (values / peaks) - 1.0
    return Decimal(str(float(drawdown.min())))


def _sharpe(equity: pd.DataFrame) -> Decimal:
    values = equity["equity"].map(float)
    returns = values.pct_change().dropna()
    std = float(returns.std(ddof=1))
    if not math.isfinite(std) or std == 0:
        return ZERO
    value = float(returns.mean()) / std * math.sqrt(engine.BARS_PER_YEAR)
    return Decimal(str(value))


def run_replay(
    candles: pd.DataFrame,
    funding: pd.DataFrame,
    filters: SymbolFilters,
    config: ReplayConfig,
    *,
    start: pd.Timestamp,
) -> ReplayResult:
    return PluginReplayEngine(candles, funding, filters, config, start=start).run()


def config_dict(config: ReplayConfig) -> dict[str, object]:
    return {
        key: str(value) if isinstance(value, Decimal) else value
        for key, value in asdict(config).items()
    }
