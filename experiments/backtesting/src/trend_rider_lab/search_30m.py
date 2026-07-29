"""Bias-controlled BTCUSDT 30-minute long/short strategy research.

This module is deliberately isolated from the production plugin registry. It searches
closed-candle signal families on public Binance USD-M data, selects only on the first
two years, and opens the final one-year holdout exactly once for the selected model.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import lru_cache
from itertools import product
from pathlib import Path
from typing import Any, Iterable, Literal

import numpy as np
import pandas as pd

from trend_rider_lab.binance_data import (
    THIRTY_MINUTES_MS,
    PublicBinanceClient,
    _write_funding,
    latest_closed_open_ms,
)

Family = Literal["ema", "momentum", "donchian", "channel", "mean_reversion", "ensemble"]
BARS_PER_YEAR = 365.2425 * 48
BASE_COST = 0.0005
WARMUP_BARS = 2_100
SEED = 20_260_729

FAMILY_OPTIONS: dict[Family, dict[str, tuple[float | int, ...]]] = {
    "ema": {
        "fast": (8, 16, 24, 48, 96, 144, 192, 288, 384),
        "slow": (96, 144, 192, 288, 384, 480, 672, 960, 1_440, 1_920),
        "band": (0.0, 0.1, 0.25, 0.5, 0.75, 1.0),
    },
    "momentum": {
        "lookback": (24, 48, 96, 144, 240, 336, 480, 672, 960, 1_440, 1_920),
        "confirm": (0, 96, 192, 384, 672, 960),
        "threshold": (0.0, 0.25, 0.5, 1.0, 1.5, 2.0),
    },
    "donchian": {
        "entry": (48, 96, 144, 240, 336, 480, 672, 960, 1_440, 1_920),
        "exit": (12, 24, 48, 96, 144, 240, 336, 480),
    },
    "channel": {
        "center": (48, 96, 144, 192, 288, 384, 480, 672, 960),
        "atr": (14, 28, 48, 96),
        "multiple": (0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0),
    },
    "mean_reversion": {
        "window": (24, 48, 72, 96, 144, 240, 336, 480, 672, 960),
        "entry_z": (1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0, 3.5),
        "exit_z": (0.0, 0.25, 0.5, 0.75, 1.0),
        "regime": (0, 192, 384, 672, 960),
    },
    "ensemble": {
        "a": (24, 48, 96, 144, 240, 336),
        "b": (144, 240, 336, 480, 672, 960),
        "c": (480, 672, 960, 1_440, 1_920),
        "votes": (1, 2, 3),
    },
}


@dataclass(frozen=True)
class Candidate:
    family: Family
    params: tuple[tuple[str, float | int], ...]

    @classmethod
    def make(cls, family: Family, values: dict[str, float | int]) -> Candidate:
        return cls(family=family, params=tuple(sorted(values.items())))

    def values(self) -> dict[str, float | int]:
        return dict(self.params)

    def label(self) -> str:
        args = ",".join(f"{key}={value}" for key, value in self.params)
        return f"{self.family}({args})"


@dataclass(frozen=True)
class WindowMetrics:
    total_return: float
    cagr: float
    sharpe: float
    max_drawdown: float
    green_months: int
    red_months: int
    flat_months: int
    worst_month: float
    best_month: float
    trades: int


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    score: float
    train: WindowMetrics
    validation: WindowMetrics
    development: WindowMetrics
    long_development_return: float
    short_development_return: float


@dataclass(frozen=True)
class SearchResult:
    candidate: Candidate
    train: WindowMetrics
    validation: WindowMetrics
    holdout: WindowMetrics
    full: WindowMetrics
    full_with_breaker: WindowMetrics
    full_long_only: WindowMetrics
    full_short_only: WindowMetrics
    stress_double_cost: WindowMetrics
    stress_one_bar_late: WindowMetrics
    monthly: tuple[tuple[str, float], ...]
    monthly_with_breaker: tuple[tuple[str, float], ...]
    candidates_broad: int
    candidates_refined: int
    candidates_total: int
    qualified_development: int
    period_start: str
    period_end: str
    train_end: str
    validation_end: str


@dataclass
class Market:
    frame: pd.DataFrame
    timestamps: pd.DatetimeIndex
    open_: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    price_returns: np.ndarray
    funding_rates: np.ndarray
    ema: dict[int, np.ndarray]
    atr: dict[int, np.ndarray]
    rolling_high: dict[int, np.ndarray]
    rolling_low: dict[int, np.ndarray]
    rolling_mean: dict[int, np.ndarray]
    rolling_std: dict[int, np.ndarray]

    @classmethod
    def load(
        cls,
        candles_path: Path,
        funding_path: Path,
        *,
        interval_minutes: int = 30,
    ) -> Market:
        if interval_minutes <= 0:
            raise ValueError("interval_minutes must be positive")
        frame = pd.read_csv(candles_path)
        frame["dt"] = pd.to_datetime(frame["dt"], utc=True)
        frame = frame.sort_values("dt").drop_duplicates("dt").reset_index(drop=True)
        steps = frame["dt"].diff().dropna()
        if not bool((steps == pd.Timedelta(minutes=interval_minutes)).all()):
            raise ValueError(
                f"{interval_minutes}-minute candle series is not continuous"
            )
        timestamps = pd.DatetimeIndex(frame["dt"])
        open_ = frame["open"].to_numpy(dtype=float)
        high = frame["high"].to_numpy(dtype=float)
        low = frame["low"].to_numpy(dtype=float)
        close = frame["close"].to_numpy(dtype=float)
        next_open = np.r_[open_[1:], close[-1]]
        price_returns = next_open / open_ - 1.0
        funding_rates = np.zeros(len(frame), dtype=float)
        funding = pd.read_csv(funding_path)
        if not funding.empty:
            funding["dt"] = pd.to_datetime(funding["dt"], utc=True, format="mixed")
            grouped = funding.groupby(funding["dt"].dt.floor(f"{interval_minutes}min"))[
                "funding_rate"
            ].sum()
            positions = timestamps.get_indexer(pd.DatetimeIndex(grouped.index))
            valid = positions >= 0
            funding_rates[positions[valid]] = grouped.to_numpy(dtype=float)[valid]
        windows: set[int] = set()
        atr_windows: set[int] = set()
        rolling_windows: set[int] = set()
        for family, options in FAMILY_OPTIONS.items():
            for name, values in options.items():
                integers = {int(value) for value in values if float(value).is_integer()}
                if family in {
                    "ema",
                    "momentum",
                    "channel",
                    "mean_reversion",
                } and name in {
                    "fast",
                    "slow",
                    "confirm",
                    "center",
                    "regime",
                }:
                    windows |= {value for value in integers if value > 0}
                if family == "channel" and name == "atr":
                    atr_windows |= integers
                if family in {"donchian", "mean_reversion"} and name in {
                    "entry",
                    "exit",
                    "window",
                }:
                    rolling_windows |= integers
        atr_windows.add(14)
        series = pd.Series(close)
        ema = {
            window: series.ewm(span=window, adjust=False).mean().to_numpy()
            for window in windows
        }
        previous_close = np.r_[np.nan, close[:-1]]
        true_range = np.maximum(
            high - low,
            np.maximum(np.abs(high - previous_close), np.abs(low - previous_close)),
        )
        atr = {
            window: pd.Series(true_range)
            .ewm(alpha=1 / window, adjust=False)
            .mean()
            .to_numpy()
            for window in atr_windows
        }
        rolling_high = {
            window: pd.Series(high).rolling(window).max().shift(1).to_numpy()
            for window in rolling_windows
        }
        rolling_low = {
            window: pd.Series(low).rolling(window).min().shift(1).to_numpy()
            for window in rolling_windows
        }
        rolling_mean = {
            window: series.rolling(window).mean().to_numpy()
            for window in rolling_windows
        }
        rolling_std = {
            window: series.rolling(window).std(ddof=0).to_numpy()
            for window in rolling_windows
        }
        return cls(
            frame=frame,
            timestamps=timestamps,
            open_=open_,
            high=high,
            low=low,
            close=close,
            price_returns=price_returns,
            funding_rates=funding_rates,
            ema=ema,
            atr=atr,
            rolling_high=rolling_high,
            rolling_low=rolling_low,
            rolling_mean=rolling_mean,
            rolling_std=rolling_std,
        )

    def signal(self, candidate: Candidate) -> np.ndarray:
        values = candidate.values()
        if candidate.family == "ema":
            fast = self.ema[int(values["fast"])]
            slow = self.ema[int(values["slow"])]
            band = float(values["band"]) * self.atr[14]
            signal = np.where(
                fast - slow > band, 1.0, np.where(slow - fast > band, -1.0, 0.0)
            )
        elif candidate.family == "momentum":
            lookback = int(values["lookback"])
            momentum = np.full(len(self.close), np.nan)
            momentum[lookback:] = self.close[lookback:] / self.close[:-lookback] - 1.0
            threshold = float(values["threshold"]) * self.atr[14] / self.close
            signal = np.where(
                momentum > threshold,
                1.0,
                np.where(momentum < -threshold, -1.0, 0.0),
            )
            confirm = int(values["confirm"])
            if confirm:
                signal = np.where(
                    (signal > 0) & (self.close > self.ema[confirm]),
                    1.0,
                    np.where(
                        (signal < 0) & (self.close < self.ema[confirm]), -1.0, 0.0
                    ),
                )
        elif candidate.family == "donchian":
            entry = int(values["entry"])
            exit_ = int(values["exit"])
            signal = _donchian_state(
                self.close,
                self.rolling_high[entry],
                self.rolling_low[entry],
                self.rolling_high[exit_],
                self.rolling_low[exit_],
            )
        elif candidate.family == "channel":
            center = self.ema[int(values["center"])]
            width = float(values["multiple"]) * self.atr[int(values["atr"])]
            signal = _channel_state(self.close, center, width)
        elif candidate.family == "mean_reversion":
            window = int(values["window"])
            zscore = (self.close - self.rolling_mean[window]) / self.rolling_std[window]
            regime = int(values["regime"])
            regime_ema = self.ema[regime] if regime else None
            signal = _mean_reversion_state(
                self.close,
                zscore,
                float(values["entry_z"]),
                float(values["exit_z"]),
                regime_ema,
            )
        else:
            horizons = [int(values[key]) for key in ("a", "b", "c")]
            votes = np.zeros(len(self.close), dtype=float)
            for lookback in horizons:
                momentum = np.full(len(self.close), np.nan)
                momentum[lookback:] = (
                    self.close[lookback:] / self.close[:-lookback] - 1.0
                )
                votes += np.sign(np.nan_to_num(momentum))
            threshold = int(values["votes"])
            signal = np.where(
                votes >= threshold, 1.0, np.where(votes <= -threshold, -1.0, 0.0)
            )
        signal[~np.isfinite(signal)] = 0.0
        return signal


def _donchian_state(
    close: np.ndarray,
    entry_high: np.ndarray,
    entry_low: np.ndarray,
    exit_high: np.ndarray,
    exit_low: np.ndarray,
) -> np.ndarray:
    out = np.zeros(len(close), dtype=float)
    state = 0.0
    for index in range(len(close)):
        if not np.isfinite(entry_high[index]):
            continue
        if close[index] > entry_high[index]:
            state = 1.0
        elif close[index] < entry_low[index]:
            state = -1.0
        elif state > 0 and close[index] < exit_low[index]:
            state = 0.0
        elif state < 0 and close[index] > exit_high[index]:
            state = 0.0
        out[index] = state
    return out


def _channel_state(
    close: np.ndarray, center: np.ndarray, width: np.ndarray
) -> np.ndarray:
    out = np.zeros(len(close), dtype=float)
    state = 0.0
    for index in range(len(close)):
        if not np.isfinite(width[index]):
            continue
        if close[index] > center[index] + width[index]:
            state = 1.0
        elif close[index] < center[index] - width[index]:
            state = -1.0
        elif state > 0 and close[index] < center[index]:
            state = 0.0
        elif state < 0 and close[index] > center[index]:
            state = 0.0
        out[index] = state
    return out


def _mean_reversion_state(
    close: np.ndarray,
    zscore: np.ndarray,
    entry_z: float,
    exit_z: float,
    regime_ema: np.ndarray | None,
) -> np.ndarray:
    out = np.zeros(len(close), dtype=float)
    state = 0.0
    for index in range(len(close)):
        z = zscore[index]
        if not np.isfinite(z):
            continue
        long_allowed = regime_ema is None or close[index] >= regime_ema[index]
        short_allowed = regime_ema is None or close[index] <= regime_ema[index]
        if state == 0:
            if z <= -entry_z and long_allowed:
                state = 1.0
            elif z >= entry_z and short_allowed:
                state = -1.0
        elif state > 0 and z >= -exit_z:
            state = 0.0
        elif state < 0 and z <= exit_z:
            state = 0.0
        out[index] = state
    return out


def strategy_returns(
    market: Market,
    signal: np.ndarray,
    *,
    cost: float = BASE_COST,
    delay_bars: int = 1,
    breaker_cap: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    if delay_bars < 1:
        raise ValueError("delay_bars must be at least one")
    desired = np.zeros(len(signal), dtype=float)
    desired[delay_bars:] = signal[:-delay_bars]
    if breaker_cap is None:
        previous = np.r_[0.0, desired[:-1]]
        turnover = np.abs(desired - previous)
        net = (
            desired * market.price_returns
            - turnover * cost
            - desired * market.funding_rates
        )
        return net, desired
    if not 0 < breaker_cap < 1:
        raise ValueError("breaker_cap must be between zero and one")
    net = np.zeros(len(signal), dtype=float)
    actual_positions = np.zeros(len(signal), dtype=float)
    position = 0.0
    month_equity = 1.0
    month: tuple[int, int] | None = None
    halted = False
    for index, timestamp in enumerate(market.timestamps):
        current_month = (timestamp.year, timestamp.month)
        if current_month != month:
            month = current_month
            month_equity = 1.0
            halted = False
        target = 0.0 if halted else desired[index]
        bar_return = (
            target * market.price_returns[index]
            - abs(target - position) * cost
            - target * market.funding_rates[index]
        )
        net[index] = bar_return
        position = target
        actual_positions[index] = target
        month_equity *= 1.0 + bar_return
        if month_equity <= 1.0 - breaker_cap:
            halted = True
    return net, actual_positions


def _window_metrics(
    timestamps: pd.DatetimeIndex,
    net: np.ndarray,
    positions: np.ndarray,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> WindowMetrics:
    mask = (timestamps >= start) & (timestamps < end)
    returns = net[mask]
    held = positions[mask]
    times = timestamps[mask]
    if len(returns) < 2 or np.any(returns <= -1):
        return WindowMetrics(-1.0, -1.0, -99.0, -1.0, 0, 0, 0, -1.0, -1.0, 0)
    equity = np.cumprod(1.0 + returns)
    total_return = float(equity[-1] - 1.0)
    days = max((times[-1] - times[0]).total_seconds() / 86_400, 1 / 48)
    cagr = float(equity[-1] ** (365.2425 / days) - 1.0) if equity[-1] > 0 else -1.0
    drawdown = equity / np.maximum.accumulate(equity) - 1.0
    daily = _compound_groups(times.floor("D"), returns)
    daily_std = float(np.std(daily, ddof=1)) if len(daily) > 1 else 0.0
    sharpe = (
        float(np.mean(daily) / daily_std * math.sqrt(365.2425)) if daily_std else 0.0
    )
    monthly = _compound_groups(times.tz_localize(None).to_period("M"), returns)
    transitions = np.r_[held[0] != 0, held[1:] != held[:-1]]
    trades = int(np.sum(transitions & (held != 0)))
    return WindowMetrics(
        total_return=total_return,
        cagr=cagr,
        sharpe=sharpe,
        max_drawdown=float(np.min(drawdown)),
        green_months=int(np.sum(monthly > 0.001)),
        red_months=int(np.sum(monthly < -0.001)),
        flat_months=int(np.sum(np.abs(monthly) <= 0.001)),
        worst_month=float(np.min(monthly)),
        best_month=float(np.max(monthly)),
        trades=trades,
    )


def _compound_groups(groups: pd.Index, returns: np.ndarray) -> np.ndarray:
    if len(returns) == 0:
        return np.array([], dtype=float)
    starts = np.r_[0, np.flatnonzero(np.asarray(groups[1:] != groups[:-1])) + 1]
    return np.expm1(np.add.reduceat(np.log1p(returns), starts))


def _monthly_rows(
    timestamps: pd.DatetimeIndex,
    net: np.ndarray,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[tuple[str, float], ...]:
    mask = (timestamps >= start) & (timestamps < end)
    times = timestamps[mask]
    month_periods = times.tz_localize(None).to_period("M")
    values = _compound_groups(month_periods, net[mask])
    months = month_periods.unique()
    return tuple(
        (str(month), float(value)) for month, value in zip(months, values, strict=True)
    )


def _score_candidate(
    market: Market,
    candidate: Candidate,
    period_start: pd.Timestamp,
    train_end: pd.Timestamp,
    validation_end: pd.Timestamp,
) -> ScoredCandidate:
    signal = market.signal(candidate)
    net, positions = strategy_returns(market, signal)
    train = _window_metrics(market.timestamps, net, positions, period_start, train_end)
    validation = _window_metrics(
        market.timestamps, net, positions, train_end, validation_end
    )
    development = _window_metrics(
        market.timestamps, net, positions, period_start, validation_end
    )
    long_net, long_pos = strategy_returns(market, np.maximum(signal, 0.0))
    short_net, short_pos = strategy_returns(market, np.minimum(signal, 0.0))
    long_metrics = _window_metrics(
        market.timestamps, long_net, long_pos, period_start, validation_end
    )
    short_metrics = _window_metrics(
        market.timestamps, short_net, short_pos, period_start, validation_end
    )
    months = development.green_months + development.red_months + development.flat_months
    green_ratio = development.green_months / months if months else 0.0
    stability = min(train.sharpe, validation.sharpe)
    score = (
        0.55 * stability
        + 0.25 * (train.sharpe + validation.sharpe)
        + 0.45 * min(train.cagr, validation.cagr)
        + 0.20 * development.cagr
        + 0.35 * green_ratio
        + 0.35 * development.max_drawdown
        - 0.15 * abs(train.cagr - validation.cagr)
    )
    if train.total_return <= 0 or validation.total_return <= 0:
        score -= 2.0
    if long_metrics.total_return <= 0:
        score -= 1.0
    if short_metrics.total_return <= 0:
        score -= 1.0
    if min(long_metrics.trades, short_metrics.trades) < 4:
        score -= 1.0
    return ScoredCandidate(
        candidate=candidate,
        score=score,
        train=train,
        validation=validation,
        development=development,
        long_development_return=long_metrics.total_return,
        short_development_return=short_metrics.total_return,
    )


def broad_candidates(count: int, *, seed: int = SEED) -> list[Candidate]:
    rng = np.random.default_rng(seed)
    universe = _candidate_universe()
    if count > len(universe):
        raise ValueError(
            f"requested {count} candidates from a universe of {len(universe)}"
        )
    selected = rng.choice(len(universe), size=count, replace=False)
    return sorted(
        (universe[int(index)] for index in selected), key=lambda item: item.label()
    )


def refined_candidates(
    leaders: Iterable[Candidate],
    count: int,
    *,
    seed: int = SEED + 1,
    exclude: Iterable[Candidate] = (),
) -> list[Candidate]:
    rng = np.random.default_rng(seed)
    leaders = tuple(leaders)
    if not leaders:
        raise ValueError("at least one leader is required")
    blocked = set(leaders) | set(exclude)
    available = [
        candidate for candidate in _candidate_universe() if candidate not in blocked
    ]
    if count > len(available):
        raise ValueError(
            f"requested {count} refinements from {len(available)} available candidates"
        )
    jitter = rng.random(len(available))
    ranked = sorted(
        zip(available, jitter, strict=True),
        key=lambda item: (_candidate_distance(item[0], leaders), item[1]),
    )
    return sorted((item[0] for item in ranked[:count]), key=lambda item: item.label())


@lru_cache(maxsize=1)
def _candidate_universe() -> tuple[Candidate, ...]:
    candidates: set[Candidate] = set()
    for family, options in FAMILY_OPTIONS.items():
        names = tuple(options)
        for combination in product(*(options[name] for name in names)):
            candidate = _valid_candidate(
                family, dict(zip(names, combination, strict=True))
            )
            if candidate is not None:
                candidates.add(candidate)
    return tuple(sorted(candidates, key=lambda item: item.label()))


def _candidate_distance(candidate: Candidate, leaders: tuple[Candidate, ...]) -> int:
    distances: list[int] = []
    values = candidate.values()
    for leader in leaders:
        if leader.family != candidate.family:
            continue
        leader_values = leader.values()
        distance = 0
        for name, value in values.items():
            options = FAMILY_OPTIONS[candidate.family][name]
            distance += abs(options.index(value) - options.index(leader_values[name]))
        distances.append(distance)
    return min(distances) if distances else 10_000


def _valid_candidate(
    family: Family,
    values: dict[str, float | int],
) -> Candidate | None:
    normalized = {
        key: int(value) if isinstance(value, (np.integer, int)) else float(value)
        for key, value in values.items()
    }
    if family == "ema" and int(normalized["fast"]) >= int(normalized["slow"]):
        return None
    if family == "donchian" and int(normalized["exit"]) >= int(normalized["entry"]):
        return None
    if family == "mean_reversion" and float(normalized["exit_z"]) >= float(
        normalized["entry_z"]
    ):
        return None
    if family == "ensemble" and not (
        int(normalized["a"]) < int(normalized["b"]) < int(normalized["c"])
    ):
        return None
    return Candidate.make(family, normalized)


def run_search(
    market: Market,
    *,
    years: int = 3,
    broad_count: int = 1_500,
    refined_count: int = 1_500,
) -> tuple[SearchResult, list[ScoredCandidate]]:
    latest = market.timestamps[-1]
    period_start = latest - pd.DateOffset(years=years)
    train_end = period_start + pd.DateOffset(years=1)
    validation_end = train_end + pd.DateOffset(years=1)
    end = latest + pd.Timedelta(minutes=30)
    broad = broad_candidates(broad_count)
    broad_scores = [
        _score_candidate(market, item, period_start, train_end, validation_end)
        for item in broad
    ]
    broad_scores.sort(key=lambda item: item.score, reverse=True)
    refined = refined_candidates(
        (item.candidate for item in broad_scores[:40]),
        refined_count,
        exclude=broad,
    )
    refined_scores = [
        _score_candidate(market, item, period_start, train_end, validation_end)
        for item in refined
    ]
    all_scores = broad_scores + refined_scores
    all_scores.sort(key=lambda item: item.score, reverse=True)
    qualified = [
        item
        for item in all_scores
        if item.train.total_return > 0
        and item.validation.total_return > 0
        and item.long_development_return > 0
        and item.short_development_return > 0
        and min(item.train.trades, item.validation.trades) >= 4
    ]
    winner = qualified[0] if qualified else all_scores[0]
    signal = market.signal(winner.candidate)
    net, positions = strategy_returns(market, signal)
    breaker_net, breaker_positions = strategy_returns(market, signal, breaker_cap=0.04)
    double_net, double_positions = strategy_returns(market, signal, cost=0.001)
    late_net, late_positions = strategy_returns(market, signal, delay_bars=2)
    long_net, long_positions = strategy_returns(market, np.maximum(signal, 0.0))
    short_net, short_positions = strategy_returns(market, np.minimum(signal, 0.0))
    result = SearchResult(
        candidate=winner.candidate,
        train=winner.train,
        validation=winner.validation,
        holdout=_window_metrics(market.timestamps, net, positions, validation_end, end),
        full=_window_metrics(market.timestamps, net, positions, period_start, end),
        full_with_breaker=_window_metrics(
            market.timestamps, breaker_net, breaker_positions, period_start, end
        ),
        full_long_only=_window_metrics(
            market.timestamps, long_net, long_positions, period_start, end
        ),
        full_short_only=_window_metrics(
            market.timestamps, short_net, short_positions, period_start, end
        ),
        stress_double_cost=_window_metrics(
            market.timestamps, double_net, double_positions, period_start, end
        ),
        stress_one_bar_late=_window_metrics(
            market.timestamps, late_net, late_positions, period_start, end
        ),
        monthly=_monthly_rows(market.timestamps, net, period_start, end),
        monthly_with_breaker=_monthly_rows(
            market.timestamps, breaker_net, period_start, end
        ),
        candidates_broad=len(broad),
        candidates_refined=len(refined),
        candidates_total=len(broad) + len(refined),
        qualified_development=len(qualified),
        period_start=period_start.isoformat(),
        period_end=latest.isoformat(),
        train_end=train_end.isoformat(),
        validation_end=validation_end.isoformat(),
    )
    return result, all_scores[:10]


def download_30m_dataset(
    data_dir: Path,
    *,
    years: int = 3,
    filename_stem: str = "btcusdt_30m",
) -> tuple[Path, Path, int]:
    if not filename_stem or any(
        char not in "abcdefghijklmnopqrstuvwxyz0123456789_" for char in filename_stem
    ):
        raise ValueError(
            "filename_stem must contain only lowercase letters, numbers, and underscores"
        )
    data_dir.mkdir(parents=True, exist_ok=True)
    client = PublicBinanceClient()
    try:
        server_time = client.server_time_ms()
        latest_open = latest_closed_open_ms(server_time, interval_ms=THIRTY_MINUTES_MS)
        latest = pd.Timestamp(latest_open, unit="ms", tz="UTC")
        start = latest - pd.DateOffset(years=years)
        warmup_start = int(start.timestamp() * 1_000) - WARMUP_BARS * THIRTY_MINUTES_MS
        candles = client.klines(
            "BTCUSDT",
            "30m",
            warmup_start,
            latest_open,
            server_time,
            interval_ms=THIRTY_MINUTES_MS,
        )
        funding = client.funding("BTCUSDT", warmup_start, server_time)
    finally:
        client.close()
    if not candles:
        raise RuntimeError("Binance returned no closed 30-minute candles")
    candles_path = data_dir / f"{filename_stem}.csv"
    funding_path = data_dir / f"{filename_stem}_funding.csv"
    _write_30m_candles(candles_path, candles)
    _write_funding(funding_path, funding)
    return candles_path, funding_path, server_time


def download_intraday_dataset(
    data_dir: Path,
    *,
    years: int,
    interval: Literal["30m", "1h"],
    filename_stem: str,
) -> tuple[Path, Path, int]:
    """Download a closed-candle intraday dataset without credentials."""
    if interval not in {"30m", "1h"}:
        raise ValueError("interval must be 30m or 1h")
    interval_minutes = 30 if interval == "30m" else 60
    interval_ms = interval_minutes * 60 * 1_000
    if not filename_stem or any(
        char not in "abcdefghijklmnopqrstuvwxyz0123456789_" for char in filename_stem
    ):
        raise ValueError(
            "filename_stem must contain only lowercase letters, numbers, and underscores"
        )
    data_dir.mkdir(parents=True, exist_ok=True)
    client = PublicBinanceClient()
    try:
        server_time = client.server_time_ms()
        latest_open = latest_closed_open_ms(server_time, interval_ms=interval_ms)
        latest = pd.Timestamp(latest_open, unit="ms", tz="UTC")
        start = latest - pd.DateOffset(years=years)
        warmup_start = int(start.timestamp() * 1_000) - WARMUP_BARS * interval_ms
        candles = client.klines(
            "BTCUSDT",
            interval,
            warmup_start,
            latest_open,
            server_time,
            interval_ms=interval_ms,
        )
        funding = client.funding("BTCUSDT", warmup_start, server_time)
    finally:
        client.close()
    if not candles:
        raise RuntimeError(f"Binance returned no closed {interval} candles")
    candles_path = data_dir / f"{filename_stem}.csv"
    funding_path = data_dir / f"{filename_stem}_funding.csv"
    _write_30m_candles(candles_path, candles)
    _write_funding(funding_path, funding)
    return candles_path, funding_path, server_time


def _write_30m_candles(path: Path, rows: list[list[Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "open_time_ms",
                "dt",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time_ms",
            ]
        )
        for row in rows:
            timestamp = int(row[0])
            writer.writerow(
                [
                    timestamp,
                    datetime.fromtimestamp(timestamp / 1_000, UTC).isoformat(),
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    int(row[6]),
                ]
            )


def write_search_result(
    result: SearchResult,
    leaders: list[ScoredCandidate],
    *,
    output_root: Path,
    candles_path: Path,
    funding_path: Path,
    server_time_ms: int,
) -> Path:
    run_id = datetime.now(UTC).strftime("30m-%Y%m%dT%H%M%SZ")
    run_dir = output_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    payload = _result_payload(result)
    payload["development_leaders"] = [
        {
            "candidate": item.candidate.label(),
            "score": item.score,
            "train": asdict(item.train),
            "validation": asdict(item.validation),
            "development": asdict(item.development),
            "long_development_return": item.long_development_return,
            "short_development_return": item.short_development_return,
        }
        for item in leaders
    ]
    (run_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_monthly_csv(
        run_dir / "monthly.csv", result.monthly, result.monthly_with_breaker
    )
    source_path = Path(__file__)
    manifest = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "binance_server_time_ms": server_time_ms,
        "seed": SEED,
        "inputs": {
            str(candles_path): _sha256(candles_path),
            str(funding_path): _sha256(funding_path),
            str(source_path): _sha256(source_path),
        },
        "selection": (
            "first year train + second year validation; final year opened only "
            "after development winner was locked"
        ),
        "assumptions": [
            "closed public Binance USD-M BTCUSDT 30-minute candles",
            "signals execute one bar later at the next open",
            "0.05% cost per unit of turnover, including fee and slippage allowance",
            "actual public funding rates applied by held direction",
            "one-times-notional exposure; no liquidation model",
            "OHLC bars cannot model order-book latency, partial fills, or ADL",
            "research only; no production plugin or account access",
        ],
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "report.md").write_text(_markdown_report(result), encoding="utf-8")
    return run_dir


def _result_payload(result: SearchResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["candidate"] = {
        "family": result.candidate.family,
        "params": dict(result.candidate.params),
        "label": result.candidate.label(),
    }
    return payload


def _write_monthly_csv(
    path: Path,
    base: tuple[tuple[str, float], ...],
    breaker: tuple[tuple[str, float], ...],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["month", "base_return", "breaker_return"])
        for (month, value), (_, breaker_value) in zip(base, breaker, strict=True):
            writer.writerow([month, value, breaker_value])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metric_line(label: str, metric: WindowMetrics) -> str:
    return (
        f"| {label} | {metric.total_return:+.2%} | {metric.cagr:+.2%} | "
        f"{metric.sharpe:.2f} | {metric.max_drawdown:.2%} | "
        f"{metric.green_months}/{metric.red_months}/{metric.flat_months} | "
        f"{metric.worst_month:+.2%} | {metric.trades} |"
    )


def _markdown_report(result: SearchResult) -> str:
    monthly = "\n".join(f"- {month}: {value:+.2%}" for month, value in result.monthly)
    return f"""# BTCUSDT 30-minute long/short research

## Locked result

- Candidate: `{result.candidate.label()}`
- Search: {result.candidates_broad} broad + {result.candidates_refined} local refinements
  = {result.candidates_total} candidates
- Development-qualified candidates: {result.qualified_development}
- Period: {result.period_start} to {result.period_end}
- Train ends: {result.train_end}
- Validation ends / untouched holdout begins: {result.validation_end}

| Window/control | Return | CAGR | Sharpe | Max DD | green/red/flat | Worst month | Trades |
|---|---:|---:|---:|---:|---:|---:|---:|
{_metric_line("Train", result.train)}
{_metric_line("Validation", result.validation)}
{_metric_line("Untouched holdout", result.holdout)}
{_metric_line("Full three years", result.full)}
{_metric_line("Full + 4% monthly breaker", result.full_with_breaker)}
{_metric_line("Long sleeve only", result.full_long_only)}
{_metric_line("Short sleeve only", result.full_short_only)}
{_metric_line("Double-cost stress", result.stress_double_cost)}
{_metric_line("One-extra-bar delay stress", result.stress_one_bar_late)}

## Monthly base returns

{monthly}

## Boundary

This is an isolated historical experiment, not a production plugin or LIVE-trading
approval. The current CryptoPilot architecture accepts only closed 4h strategies.
Historical results do not guarantee future performance, and a single three-year
BTC sample cannot establish that any strategy will be profitable every month.
"""
