"""Six-year asymmetric sleeve research with a latest-three-year evaluation.

The older three years select long and short sleeves independently. Only the locked
composite is then evaluated on the latest three years requested by the owner.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from trend_rider_lab.search_30m import (
    BASE_COST,
    Candidate,
    Family,
    Market,
    _candidate_universe,
    strategy_returns,
)

Side = Literal["LONG", "SHORT"]
WEIGHTS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
MAX_EXPOSURE = 2.0


@dataclass(frozen=True)
class Metrics:
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
class Window:
    start: pd.Timestamp
    end: pd.Timestamp
    first: int
    last: int
    daily_starts: np.ndarray
    monthly_starts: np.ndarray
    month_labels: tuple[str, ...]

    @classmethod
    def make(
        cls,
        timestamps: pd.DatetimeIndex,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> Window:
        first = int(timestamps.searchsorted(start, side="left"))
        last = int(timestamps.searchsorted(end, side="left"))
        if last - first < 2:
            raise ValueError("research window must contain at least two bars")
        times = timestamps[first:last]
        daily = times.floor("D").astype(str).to_numpy()
        monthly_index = times.tz_localize(None).to_period("M")
        monthly = monthly_index.astype(str).to_numpy()
        return cls(
            start=start,
            end=end,
            first=first,
            last=last,
            daily_starts=_group_starts(daily),
            monthly_starts=_group_starts(monthly),
            month_labels=tuple(str(value) for value in monthly_index.unique()),
        )

    def metrics(self, net: np.ndarray, positions: np.ndarray) -> Metrics:
        returns = net[self.first : self.last]
        held = positions[self.first : self.last]
        if np.any(returns <= -1):
            return Metrics(-1.0, -1.0, -99.0, -1.0, 0, 0, 0, -1.0, -1.0, 0)
        equity = np.cumprod(1.0 + returns)
        total_return = float(equity[-1] - 1.0)
        duration_days = max(
            (self.end - self.start).total_seconds() / 86_400,
            1 / 48,
        )
        cagr = (
            float(equity[-1] ** (365.2425 / duration_days) - 1.0)
            if equity[-1] > 0
            else -1.0
        )
        drawdown = equity / np.maximum.accumulate(equity) - 1.0
        log_returns = np.log1p(returns)
        daily = np.expm1(np.add.reduceat(log_returns, self.daily_starts))
        monthly = np.expm1(np.add.reduceat(log_returns, self.monthly_starts))
        daily_std = float(np.std(daily, ddof=1)) if len(daily) > 1 else 0.0
        sharpe = (
            float(np.mean(daily) / daily_std * math.sqrt(365.2425))
            if daily_std
            else 0.0
        )
        transitions = np.r_[held[0] != 0, held[1:] != held[:-1]]
        return Metrics(
            total_return=total_return,
            cagr=cagr,
            sharpe=sharpe,
            max_drawdown=float(np.min(drawdown)),
            green_months=int(np.sum(monthly > 0.001)),
            red_months=int(np.sum(monthly < -0.001)),
            flat_months=int(np.sum(np.abs(monthly) <= 0.001)),
            worst_month=float(np.min(monthly)),
            best_month=float(np.max(monthly)),
            trades=int(np.sum(transitions & (held != 0))),
        )

    def monthly(self, net: np.ndarray) -> tuple[tuple[str, float], ...]:
        returns = net[self.first : self.last]
        values = np.expm1(np.add.reduceat(np.log1p(returns), self.monthly_starts))
        return tuple(
            zip(self.month_labels, (float(value) for value in values), strict=True)
        )


@dataclass(frozen=True)
class SleeveScore:
    candidate: Candidate
    side: Side
    score: float
    development: Metrics
    folds: tuple[Metrics, ...]


@dataclass(frozen=True)
class CompositeScore:
    long_candidate: Candidate
    short_candidate: Candidate
    long_weight: float
    short_weight: float
    score: float
    development: Metrics
    folds: tuple[Metrics, ...]

    def label(self) -> str:
        return (
            f"long={self.long_candidate.label()}@{self.long_weight:g};"
            f"short={self.short_candidate.label()}@{self.short_weight:g}"
        )


@dataclass(frozen=True)
class AsymmetricResult:
    winner: CompositeScore
    timeframe_minutes: int
    families: tuple[str, ...]
    development_start: str
    evaluation_start: str
    evaluation_end: str
    candidates_evaluated: int
    long_leaders: int
    short_leaders: int
    composites_evaluated: int
    evaluation: Metrics
    evaluation_long_only: Metrics
    evaluation_short_only: Metrics
    evaluation_double_cost: Metrics
    evaluation_extra_delay: Metrics
    evaluation_breaker: Metrics
    evaluation_unit_cap: Metrics
    evaluation_unit_cap_breaker: Metrics
    evaluation_monthly: tuple[tuple[str, float], ...]
    full_six_year: Metrics


def _group_starts(values: np.ndarray) -> np.ndarray:
    return np.r_[0, np.flatnonzero(values[1:] != values[:-1]) + 1]


def _score_metrics(development: Metrics, folds: tuple[Metrics, ...]) -> float:
    months = development.green_months + development.red_months + development.flat_months
    green_ratio = development.green_months / months if months else 0.0
    fold_sharpes = np.array([metric.sharpe for metric in folds])
    fold_cagrs = np.array([metric.cagr for metric in folds])
    score = (
        0.45 * float(np.median(fold_sharpes))
        + 0.25 * float(np.min(fold_sharpes))
        + 0.25 * development.sharpe
        + 0.55 * float(np.min(fold_cagrs))
        + 0.25 * development.cagr
        + 0.45 * green_ratio
        + 0.30 * development.max_drawdown
    )
    score -= 0.5 * float(np.std(fold_cagrs))
    score -= 0.25 * development.red_months / max(months, 1)
    return score


def _score_sleeve(
    market: Market,
    candidate: Candidate,
    side: Side,
    development: Window,
    folds: tuple[Window, ...],
    *,
    signal: np.ndarray | None = None,
) -> SleeveScore:
    if signal is None:
        signal = market.signal(candidate)
    sleeve_signal = (
        np.maximum(signal, 0.0) if side == "LONG" else np.minimum(signal, 0.0)
    )
    net, positions = strategy_returns(market, sleeve_signal)
    development_metrics = development.metrics(net, positions)
    fold_metrics = tuple(window.metrics(net, positions) for window in folds)
    score = _score_metrics(development_metrics, fold_metrics)
    positive_folds = sum(metric.total_return > 0 for metric in fold_metrics)
    if development_metrics.total_return <= 0:
        score -= 3.0
    if positive_folds < 2:
        score -= 1.5
    if development_metrics.trades < 8:
        score -= 1.0
    if min(metric.total_return for metric in fold_metrics) < -0.15:
        score -= 1.0
    return SleeveScore(
        candidate=candidate,
        side=side,
        score=score,
        development=development_metrics,
        folds=fold_metrics,
    )


def _composite_target(
    long_signal: np.ndarray,
    short_signal: np.ndarray,
    long_weight: float,
    short_weight: float,
    *,
    max_exposure: float = MAX_EXPOSURE,
) -> np.ndarray:
    weighted_long = np.maximum(long_signal, 0.0) * long_weight
    weighted_short = np.minimum(short_signal, 0.0) * short_weight
    return np.clip(weighted_long + weighted_short, -max_exposure, max_exposure)


def _score_composite(
    market: Market,
    long_candidate: Candidate,
    short_candidate: Candidate,
    long_weight: float,
    short_weight: float,
    development: Window,
    folds: tuple[Window, ...],
    *,
    long_signal: np.ndarray,
    short_signal: np.ndarray,
) -> CompositeScore:
    target = _composite_target(
        long_signal,
        short_signal,
        long_weight,
        short_weight,
    )
    net, positions = strategy_returns(market, target)
    development_metrics = development.metrics(net, positions)
    fold_metrics = tuple(window.metrics(net, positions) for window in folds)
    score = _score_metrics(development_metrics, fold_metrics)
    if development_metrics.total_return <= 0:
        score -= 5.0
    if sum(metric.total_return > 0 for metric in fold_metrics) < 2:
        score -= 2.0
    if development_metrics.max_drawdown < -0.45:
        score -= 2.0
    if development_metrics.trades < 12:
        score -= 1.0
    return CompositeScore(
        long_candidate=long_candidate,
        short_candidate=short_candidate,
        long_weight=long_weight,
        short_weight=short_weight,
        score=score,
        development=development_metrics,
        folds=fold_metrics,
    )


def run_asymmetric_search(
    market: Market,
    *,
    leader_count: int = 12,
    timeframe_minutes: int = 30,
    allowed_families: frozenset[Family] | None = None,
) -> tuple[AsymmetricResult, list[SleeveScore], list[SleeveScore]]:
    if timeframe_minutes <= 0:
        raise ValueError("timeframe_minutes must be positive")
    latest = market.timestamps[-1]
    development_start = latest - pd.DateOffset(years=6)
    evaluation_start = latest - pd.DateOffset(years=3)
    evaluation_end = latest + pd.Timedelta(minutes=timeframe_minutes)
    development = Window.make(market.timestamps, development_start, evaluation_start)
    evaluation = Window.make(market.timestamps, evaluation_start, evaluation_end)
    full = Window.make(market.timestamps, development_start, evaluation_end)
    folds = tuple(
        Window.make(
            market.timestamps,
            development_start + pd.DateOffset(years=index),
            development_start + pd.DateOffset(years=index + 1),
        )
        for index in range(3)
    )

    candidates = _selected_candidates(allowed_families)
    long_scores: list[SleeveScore] = []
    short_scores: list[SleeveScore] = []
    for candidate in candidates:
        signal = market.signal(candidate)
        long_scores.append(
            _score_sleeve(
                market,
                candidate,
                "LONG",
                development,
                folds,
                signal=signal,
            )
        )
        short_scores.append(
            _score_sleeve(
                market,
                candidate,
                "SHORT",
                development,
                folds,
                signal=signal,
            )
        )
    long_scores.sort(key=lambda item: item.score, reverse=True)
    short_scores.sort(key=lambda item: item.score, reverse=True)
    long_leaders = long_scores[:leader_count]
    short_leaders = short_scores[:leader_count]
    leader_candidates = {item.candidate for item in long_leaders} | {
        item.candidate for item in short_leaders
    }
    leader_signals = {
        candidate: market.signal(candidate) for candidate in leader_candidates
    }

    composites = [
        _score_composite(
            market,
            long_leader.candidate,
            short_leader.candidate,
            long_weight,
            short_weight,
            development,
            folds,
            long_signal=leader_signals[long_leader.candidate],
            short_signal=leader_signals[short_leader.candidate],
        )
        for long_leader in long_leaders
        for short_leader in short_leaders
        for long_weight in WEIGHTS
        for short_weight in WEIGHTS
    ]
    composites.sort(key=lambda item: item.score, reverse=True)
    winner = composites[0]
    target = _composite_target(
        leader_signals[winner.long_candidate],
        leader_signals[winner.short_candidate],
        winner.long_weight,
        winner.short_weight,
    )
    net, positions = strategy_returns(market, target)
    breaker_net, breaker_positions = strategy_returns(
        market,
        target,
        breaker_cap=0.04,
    )
    double_net, double_positions = strategy_returns(
        market,
        target,
        cost=BASE_COST * 2,
    )
    delayed_net, delayed_positions = strategy_returns(
        market,
        target,
        delay_bars=2,
    )
    unit_target = np.clip(target, -1.0, 1.0)
    unit_net, unit_positions = strategy_returns(market, unit_target)
    unit_breaker_net, unit_breaker_positions = strategy_returns(
        market,
        unit_target,
        breaker_cap=0.04,
    )
    long_target = (
        np.maximum(leader_signals[winner.long_candidate], 0.0) * winner.long_weight
    )
    short_target = (
        np.minimum(leader_signals[winner.short_candidate], 0.0) * winner.short_weight
    )
    long_net, long_positions = strategy_returns(market, long_target)
    short_net, short_positions = strategy_returns(market, short_target)
    result = AsymmetricResult(
        winner=winner,
        timeframe_minutes=timeframe_minutes,
        families=tuple(sorted({candidate.family for candidate in candidates})),
        development_start=development_start.isoformat(),
        evaluation_start=evaluation_start.isoformat(),
        evaluation_end=latest.isoformat(),
        candidates_evaluated=len(candidates),
        long_leaders=len(long_leaders),
        short_leaders=len(short_leaders),
        composites_evaluated=len(composites),
        evaluation=evaluation.metrics(net, positions),
        evaluation_long_only=evaluation.metrics(long_net, long_positions),
        evaluation_short_only=evaluation.metrics(short_net, short_positions),
        evaluation_double_cost=evaluation.metrics(double_net, double_positions),
        evaluation_extra_delay=evaluation.metrics(delayed_net, delayed_positions),
        evaluation_breaker=evaluation.metrics(breaker_net, breaker_positions),
        evaluation_unit_cap=evaluation.metrics(unit_net, unit_positions),
        evaluation_unit_cap_breaker=evaluation.metrics(
            unit_breaker_net,
            unit_breaker_positions,
        ),
        evaluation_monthly=evaluation.monthly(net),
        full_six_year=full.metrics(net, positions),
    )
    return result, long_leaders, short_leaders


def _selected_candidates(
    allowed_families: frozenset[Family] | None,
) -> tuple[Candidate, ...]:
    candidates = _candidate_universe()
    if allowed_families is not None:
        candidates = tuple(
            candidate
            for candidate in candidates
            if candidate.family in allowed_families
        )
    if not candidates:
        raise ValueError("allowed_families selected no candidates")
    return candidates


def write_asymmetric_result(
    result: AsymmetricResult,
    long_leaders: list[SleeveScore],
    short_leaders: list[SleeveScore],
    *,
    output_root: Path,
    candles_path: Path,
    funding_path: Path,
    server_time_ms: int,
) -> Path:
    timeframe = _timeframe_label(result.timeframe_minutes)
    variant = "trend" if "mean_reversion" not in result.families else "all"
    run_id = datetime.now(UTC).strftime(
        f"{timeframe}-asymmetric-{variant}-%Y%m%dT%H%M%SZ"
    )
    run_dir = output_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    payload = asdict(result)
    payload["winner"]["label"] = result.winner.label()
    payload["long_leaders_detail"] = [
        {
            "candidate": item.candidate.label(),
            "score": item.score,
            "development": asdict(item.development),
            "folds": [asdict(metric) for metric in item.folds],
        }
        for item in long_leaders
    ]
    payload["short_leaders_detail"] = [
        {
            "candidate": item.candidate.label(),
            "score": item.score,
            "development": asdict(item.development),
            "folds": [asdict(metric) for metric in item.folds],
        }
        for item in short_leaders
    ]
    (run_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "report.md").write_text(_markdown_report(result), encoding="utf-8")
    source_path = Path(__file__)
    manifest = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "binance_server_time_ms": server_time_ms,
        "inputs": {
            str(candles_path): _sha256(candles_path),
            str(funding_path): _sha256(funding_path),
            str(source_path): _sha256(source_path),
        },
        "selection": (
            "older three years select independent long and short sleeves across "
            "three annual folds; latest three years evaluate the locked composite"
        ),
        "assumptions": [
            f"closed public Binance USD-M BTCUSDT {timeframe} candles",
            f"signals execute at the next {timeframe} open",
            "0.05% turnover cost plus actual public funding",
            "net one-way exposure clipped to two-times notional",
            "no order-book, partial-fill, ADL, or liquidation simulation",
            "research only; no account access or production registration",
        ],
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return run_dir


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metric_row(label: str, metric: Metrics) -> str:
    return (
        f"| {label} | {metric.total_return:+.2%} | {metric.cagr:+.2%} | "
        f"{metric.sharpe:.2f} | {metric.max_drawdown:.2%} | "
        f"{metric.green_months}/{metric.red_months}/{metric.flat_months} | "
        f"{metric.worst_month:+.2%} | {metric.trades} |"
    )


def _timeframe_label(minutes: int) -> str:
    return f"{minutes // 60}h" if minutes % 60 == 0 else f"{minutes}m"


def _markdown_report(result: AsymmetricResult) -> str:
    timeframe = _timeframe_label(result.timeframe_minutes)
    monthly = "\n".join(
        f"- {month}: {value:+.2%}" for month, value in result.evaluation_monthly
    )
    return f"""# BTCUSDT {timeframe} asymmetric sleeve research

## Locked composite

- `{result.winner.label()}`
- Older-data development: {result.development_start} to {result.evaluation_start}
- Latest-three-year evaluation: {result.evaluation_start} to {result.evaluation_end}
- Sleeve candidates: {result.candidates_evaluated} long + {result.candidates_evaluated} short
- Families: {", ".join(result.families)}
- Composite combinations: {result.composites_evaluated}

| Window/control | Return | CAGR | Sharpe | Max DD | green/red/flat | Worst month | Trades |
|---|---:|---:|---:|---:|---:|---:|---:|
{_metric_row("Older three-year development", result.winner.development)}
{_metric_row("Latest three-year evaluation", result.evaluation)}
{_metric_row("Evaluation long sleeve", result.evaluation_long_only)}
{_metric_row("Evaluation short sleeve", result.evaluation_short_only)}
{_metric_row("Evaluation double cost", result.evaluation_double_cost)}
{_metric_row(f"Evaluation extra {timeframe} delay", result.evaluation_extra_delay)}
{_metric_row("Evaluation 4% monthly breaker", result.evaluation_breaker)}
{_metric_row("Evaluation 1x cap", result.evaluation_unit_cap)}
{_metric_row("Evaluation 1x cap + breaker", result.evaluation_unit_cap_breaker)}
{_metric_row("Full six years", result.full_six_year)}

## Latest-three-year monthly returns

{monthly}

## Boundary

The latest three years are an evaluation of an older-data-selected composite, but this
research follows an earlier experiment that already inspected the same recent market.
Treat the result as stronger evidence than an in-sample fit, not as a pristine first-use
holdout or a guarantee. It is not a production plugin or LIVE authorization.
"""
