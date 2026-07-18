"""Independent monthly circuit breakers (BSD FR-08), Decimal math.

Two independent breakers, each tripping at -4% month-to-date:
  - LONG book: flatten longs + halt long entries until the 1st.
  - SHORT sleeve: cover + halt shorts until the 1st.
They reset independently at the start of each calendar month. State is derived
from persisted equity snapshots so restarts cannot forget a tripped breaker.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

DEFAULT_CAP = Decimal("0.04")  # 4% month-to-date


@dataclass(frozen=True)
class BreakerState:
    tripped: bool
    month_to_date_pnl: Decimal
    month_start_equity: Decimal
    threshold: Decimal  # negative absolute equity level that trips it

    @property
    def drawdown_pct(self) -> Decimal:
        if self.month_start_equity <= 0:
            return Decimal("0")
        return self.month_to_date_pnl / self.month_start_equity


def evaluate_breaker(
    *,
    month_start_equity: Decimal,
    month_to_date_pnl: Decimal,
    cap: Decimal = DEFAULT_CAP,
) -> BreakerState:
    """Return the breaker state for one book given its month-to-date P&L.

    Trips when the book has lost `cap` (default 4%) of the month-start equity.
    """
    threshold = -(cap * month_start_equity)
    tripped = month_start_equity > 0 and month_to_date_pnl <= threshold
    return BreakerState(
        tripped=tripped,
        month_to_date_pnl=month_to_date_pnl,
        month_start_equity=month_start_equity,
        threshold=threshold,
    )


def is_new_month(prev_month: tuple[int, int] | None, current: tuple[int, int]) -> bool:
    """True when `current` (year, month) differs from `prev_month`."""
    return prev_month is None or prev_month != current
