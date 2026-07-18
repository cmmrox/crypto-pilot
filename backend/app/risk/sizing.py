"""Position sizing (Decimal). The risk engine owns sizing — strategies never size.

Long: risk % of equity per trade, divided by the stop distance, capped by leverage.
Short sleeve: weight% x min(1, vol_target/realized_vol) of equity, capped by leverage.
Both round DOWN to the exchange lot size and respect min-notional.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.execution.filters import SymbolFilters, clamp_qty, meets_min_notional


@dataclass(frozen=True)
class SizingResult:
    qty: Decimal
    notional: Decimal
    leverage: Decimal
    ok: bool
    reason: str


def _leverage_capped_qty(
    qty: Decimal, price: Decimal, equity: Decimal, leverage_cap: Decimal
) -> Decimal:
    """Reduce qty so that notional / equity never exceeds the leverage cap."""
    if equity <= 0 or price <= 0:
        return Decimal("0")
    max_notional = equity * leverage_cap
    if qty * price > max_notional:
        return max_notional / price
    return qty


def size_long(
    *,
    equity: Decimal,
    risk_pct: Decimal,
    stop_distance: Decimal,
    price: Decimal,
    leverage_cap: Decimal,
    filters: SymbolFilters,
) -> SizingResult:
    """Size a long: qty = (equity * risk%) / stop_distance, leverage-capped."""
    if stop_distance <= 0 or price <= 0 or equity <= 0:
        return SizingResult(Decimal("0"), Decimal("0"), Decimal("0"), False, "invalid inputs")
    risk_capital = equity * (risk_pct / Decimal("100"))
    raw_qty = risk_capital / stop_distance
    raw_qty = _leverage_capped_qty(raw_qty, price, equity, leverage_cap)
    qty = clamp_qty(raw_qty, filters)
    if qty <= 0:
        return SizingResult(Decimal("0"), Decimal("0"), Decimal("0"), False, "below min lot")
    if not meets_min_notional(qty, price, filters):
        return SizingResult(qty, qty * price, Decimal("0"), False, "below min notional")
    notional = qty * price
    return SizingResult(qty, notional, notional / equity, True, "ok")


def sleeve_scale(vol_target: Decimal, realized_vol: Decimal) -> Decimal:
    """Vol-targeting scale = min(1, vol_target / realized_vol); 0 if vol invalid."""
    if realized_vol <= 0:
        return Decimal("0")
    return min(Decimal("1"), vol_target / realized_vol)


def size_short(
    *,
    equity: Decimal,
    weight_pct: Decimal,
    vol_target: Decimal,
    realized_vol: Decimal,
    price: Decimal,
    leverage_cap: Decimal,
    filters: SymbolFilters,
) -> SizingResult:
    """Size the vol-targeted short sleeve.

    notional = equity * weight% * min(1, vol_target/realized_vol), leverage-capped.
    """
    if price <= 0 or equity <= 0:
        return SizingResult(Decimal("0"), Decimal("0"), Decimal("0"), False, "invalid inputs")
    scale = sleeve_scale(vol_target, realized_vol)
    if scale <= 0:
        return SizingResult(Decimal("0"), Decimal("0"), Decimal("0"), False, "vol scale zero")
    notional = equity * (weight_pct / Decimal("100")) * scale
    raw_qty = notional / price
    raw_qty = _leverage_capped_qty(raw_qty, price, equity, leverage_cap)
    qty = clamp_qty(raw_qty, filters)
    if qty <= 0:
        return SizingResult(Decimal("0"), Decimal("0"), Decimal("0"), False, "below min lot")
    if not meets_min_notional(qty, price, filters):
        return SizingResult(qty, qty * price, Decimal("0"), False, "below min notional")
    final_notional = qty * price
    return SizingResult(qty, final_notional, final_notional / equity, True, "ok")
