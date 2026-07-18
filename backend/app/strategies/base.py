"""Strategy plugin contract: abstract intents, protocol, and registry (BSD §7).

Strategies are PURE: given candles + trade state they return abstract intents and
never touch Binance, size positions, or perform I/O. The execution engine owns
sizing, exchange filters, and order mechanics.

Numeric note: strategy *decisions* use float to reproduce the validated research
engine bar-for-bar (the parity gate). Money/quantities become Decimal at the
execution boundary — the strategy only emits multiples/distances/exposures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# --- Intents (the complete vocabulary — do not extend casually) ---


@dataclass(frozen=True)
class EnterLong:
    """Open a long. The engine sizes from risk % and places stop + TP orders."""

    stop_distance: float  # price distance (entry - stop), = stop_atr * ATR
    tp_levels: tuple[tuple[float, float], ...]  # ((r_multiple, fraction), ...)
    reason: str = "regime"


@dataclass(frozen=True)
class EnterShort:
    """Open the vol-sized short sleeve. No price stop by validated design."""

    weight: float  # sleeve weight fraction of equity (e.g. 0.75)
    vol_target: float  # annualized vol target (e.g. 0.40)
    reason: str = "deep_bear"


@dataclass(frozen=True)
class ResizeShort:
    """Adjust the short toward its vol target (engine applies the drift guard)."""

    target_weight: float  # desired fraction of equity (already vol-scaled)
    reason: str = "vol_drift"


@dataclass(frozen=True)
class MoveStop:
    """Ratchet the protective stop (engine refuses to lower a long stop)."""

    price: float


@dataclass(frozen=True)
class TakePartial:
    """Informational: a TP level was reached (TP orders rest on the exchange)."""

    level_id: int


@dataclass(frozen=True)
class ExitAll:
    """Flatten everything (regime death, breaker, manual, kill)."""

    reason: str


@dataclass(frozen=True)
class Halt:
    """Stand aside until `until` (monthly breaker)."""

    until: str  # ISO month or date


Intent = EnterLong | EnterShort | ResizeShort | MoveStop | TakePartial | ExitAll | Halt


# --- Candle window + trade state passed to the strategy ---


@dataclass(frozen=True)
class Candle:
    """One closed candle (floats for indicator math; UTC ms open time)."""

    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class TradeState:
    """Account/position context the engine gives the strategy each bar."""

    equity: float
    long_position: bool = False
    short_weight: float = 0.0  # current short exposure fraction (>=0)
    long_stop: float | None = None
    tp1_done: bool = False
    halted_long: bool = False
    halted_short: bool = False
    extra: dict[str, float] = field(default_factory=dict)


@runtime_checkable
class Strategy(Protocol):
    """The plugin interface. Implementations must be pure and deterministic."""

    name: str
    params: dict[str, float]

    def warmup_bars(self) -> int:
        """History required before the first decision (v6: 200 for SMA200)."""
        ...

    def on_candle(self, candles: list[Candle], state: TradeState) -> list[Intent]:
        """Return intents for the just-closed candle (candles[-1])."""
        ...


# --- Registry ---

_REGISTRY: dict[str, Strategy] = {}


def register(strategy: Strategy) -> Strategy:
    """Register a strategy by its name."""
    _REGISTRY[strategy.name] = strategy
    return strategy


def get_strategy(name: str) -> Strategy:
    if name not in _REGISTRY:
        raise KeyError(f"strategy not registered: {name}")
    return _REGISTRY[name]


def registered_names() -> list[str]:
    return sorted(_REGISTRY)
