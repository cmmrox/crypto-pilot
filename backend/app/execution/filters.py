"""Binance exchange-filter rounding (Decimal money math).

Quantities round DOWN to stepSize (never over-order); prices round to tickSize.
Min-notional is enforced. All inputs/outputs are Decimal — never float.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class SymbolFilters:
    """Lot/price/notional filters for a symbol (from exchangeInfo)."""

    step_size: Decimal
    min_qty: Decimal
    max_qty: Decimal
    tick_size: Decimal
    min_notional: Decimal

    @classmethod
    def from_exchange(cls, filters: dict[str, dict[str, object]]) -> SymbolFilters:
        """Build from a {filterType: filter} mapping (BinanceClient.get_exchange_filters).

        Prefers MARKET_LOT_SIZE for step/qty (we place MARKET orders), falling back
        to LOT_SIZE.
        """
        lot = filters.get("MARKET_LOT_SIZE") or filters["LOT_SIZE"]
        price = filters["PRICE_FILTER"]
        notional = filters.get("MIN_NOTIONAL", {"notional": "0"})
        return cls(
            step_size=Decimal(str(lot["stepSize"])),
            min_qty=Decimal(str(lot["minQty"])),
            max_qty=Decimal(str(lot["maxQty"])),
            tick_size=Decimal(str(price["tickSize"])),
            min_notional=Decimal(str(notional.get("notional", "0"))),
        )


def round_qty(qty: Decimal, step: Decimal) -> Decimal:
    """Round a quantity DOWN to the exchange step size."""
    if step <= 0:
        return qty
    return (qty // step) * step


def round_price(price: Decimal, tick: Decimal) -> Decimal:
    """Round a price to the nearest tick size (half-up)."""
    if tick <= 0:
        return price
    return (price / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick


def clamp_qty(qty: Decimal, filters: SymbolFilters) -> Decimal:
    """Round down to step and clamp to [0, max_qty]; below min_qty → 0."""
    q = round_qty(qty, filters.step_size)
    if q > filters.max_qty:
        q = round_qty(filters.max_qty, filters.step_size)
    if q < filters.min_qty:
        return Decimal("0")
    return q


def meets_min_notional(qty: Decimal, price: Decimal, filters: SymbolFilters) -> bool:
    """True if qty*price satisfies the exchange min-notional."""
    return qty * price >= filters.min_notional


def quantize_money(value: Decimal, places: str = "0.00000001") -> Decimal:
    """Quantize a money value to 8 dp (numeric(20,8)), rounding down."""
    return value.quantize(Decimal(places), rounding=ROUND_DOWN)
