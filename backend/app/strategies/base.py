"""Public compatibility imports and backend-owned strategy registry."""

from strategy_runtime.contracts import (
    Candle as Candle,
)
from strategy_runtime.contracts import (
    EnterLong as EnterLong,
)
from strategy_runtime.contracts import (
    EnterShort as EnterShort,
)
from strategy_runtime.contracts import (
    EnterShortStop as EnterShortStop,
)
from strategy_runtime.contracts import (
    ExitAll as ExitAll,
)
from strategy_runtime.contracts import (
    Halt as Halt,
)
from strategy_runtime.contracts import (
    Intent as Intent,
)
from strategy_runtime.contracts import (
    MoveStop as MoveStop,
)
from strategy_runtime.contracts import (
    ResizeShort as ResizeShort,
)
from strategy_runtime.contracts import (
    Strategy as Strategy,
)
from strategy_runtime.contracts import (
    StrategyWatch as StrategyWatch,
)
from strategy_runtime.contracts import (
    TakePartial as TakePartial,
)
from strategy_runtime.contracts import (
    TradeState as TradeState,
)
from strategy_runtime.contracts import (
    WatchRule as WatchRule,
)

_REGISTRY: dict[str, Strategy] = {}
_ALIASES: dict[str, str] = {}


def register(strategy: Strategy) -> Strategy:
    """Register one canonical strategy and its persisted legacy aliases."""
    strategy_id = strategy.manifest.strategy_id
    if strategy_id in _REGISTRY or strategy_id in _ALIASES:
        raise RuntimeError(f"strategy already registered: {strategy_id}")
    _REGISTRY[strategy_id] = strategy
    for alias in strategy.manifest.legacy_ids:
        if alias in _ALIASES or alias in _REGISTRY:
            raise RuntimeError(f"strategy alias already registered: {alias}")
        _ALIASES[alias] = strategy_id
    return strategy


def get_registered(name: str) -> Strategy:
    canonical = _ALIASES.get(name, name)
    if canonical not in _REGISTRY:
        raise KeyError(f"strategy not registered: {name}")
    return _REGISTRY[canonical]


def registered_items() -> tuple[tuple[str, Strategy], ...]:
    return tuple(sorted(_REGISTRY.items()))
