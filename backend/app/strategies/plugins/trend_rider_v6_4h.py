"""Immutable production wrapper around the shared, parity-tested runtime."""

from strategy_runtime.trend_rider import TrendRider

from app.strategies.base import Strategy, register


class TrendRiderV6(TrendRider):
    """Keep the approved production release's constructor and parameters pinned."""

    def __init__(self) -> None:
        super().__init__()


PLUGIN: Strategy = register(TrendRiderV6())
