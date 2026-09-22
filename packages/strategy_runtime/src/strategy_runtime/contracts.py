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

from strategy_runtime.manifest import StrategyManifest

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
class EnterShortStop:
    """Open a stop-protected short: the engine sizes from risk % / stop distance.

    Added for releases whose short book carries a protective price stop and a
    partial take-profit, mirroring ``EnterLong``. ``EnterShort`` (the stop-free,
    vol-sized sleeve used by Trend Rider v6) is unchanged and still valid.
    """

    stop_distance: float  # price distance (stop - entry), = stop_atr * ATR
    tp_levels: tuple[tuple[float, float], ...]  # ((r_multiple, fraction), ...)
    reason: str = "regime"


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


Intent = (
    EnterLong
    | EnterShort
    | EnterShortStop
    | ResizeShort
    | MoveStop
    | TakePartial
    | ExitAll
    | Halt
)


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
    long_entry: float | None = None
    long_stop: float | None = None
    highest_high: float | None = None
    tp1_done: bool = False
    last_long_closed_at_ms: int | None = None
    halted_long: bool = False
    halted_short: bool = False
    # Stop-protected short book (releases that pair EnterShortStop with MoveStop).
    # Stop-free sleeve releases leave these at their defaults.
    short_position: bool = False
    short_entry: float | None = None
    short_stop: float | None = None
    lowest_low: float | None = None
    last_short_closed_at_ms: int | None = None
    extra: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class WatchRule:
    """One strategy-owned, read-only condition shown in the owner console."""

    key: str
    label: str
    status: str
    tone: str
    active: bool
    condition: str
    threshold: float | None


@dataclass(frozen=True)
class StrategyWatch:
    """Generic explainability projection for the latest closed candle."""

    last_closed_open_time_ms: int
    rules: tuple[WatchRule, ...]
    disclaimer: str


@runtime_checkable
class Strategy(Protocol):
    """The plugin interface. Implementations must be pure and deterministic."""

    params: dict[str, float]
    manifest: StrategyManifest

    def on_candle(self, candles: list[Candle], state: TradeState) -> list[Intent]:
        """Return intents for the just-closed candle (candles[-1])."""
        ...

    def inspect(self, candles: list[Candle]) -> StrategyWatch | None:
        """Explain the latest closed-candle state without emitting intents."""
        ...
