"""Position sizing (Decimal). The risk engine owns sizing — strategies never size.

Long: risk % of equity per trade, divided by the stop distance, capped by leverage.
Short sleeve: weight% x min(1, vol_target/realized_vol) of equity, capped by leverage.
Both round DOWN to the exchange lot size and respect min-notional.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from strategy_runtime.filters import SymbolFilters, clamp_qty, meets_min_notional

# Binance charges the taker fee on the entry fill, on top of the initial margin.
# Take the conservative side of the maker/taker schedule so the reserve never
# under-provides.
TAKER_FEE_RATE = Decimal("0.0005")
# Held back from available balance so a leverage-capped entry stays placeable
# through mark-price drift between sizing and the fill.
MARGIN_SAFETY_BUFFER = Decimal("0.02")


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


def margin_capped_qty(
    qty: Decimal, price: Decimal, available_margin: Decimal, leverage_cap: Decimal
) -> Decimal:
    """Reduce qty so the entry's initial margin plus taker fee actually fit.

    The account's configured leverage equals `leverage_cap`, so a notional sized
    to exactly the cap needs `notional / leverage_cap` = the entire balance as
    initial margin and the exchange rejects the order for fees alone (Binance
    -2019). This is a placeability constraint on top of the risk cap, never a
    relaxation of it: it only ever lowers quantity.
    """
    if available_margin <= 0 or price <= 0 or leverage_cap <= 0:
        return Decimal("0")
    spendable = available_margin * (Decimal("1") - MARGIN_SAFETY_BUFFER)
    cost_per_notional = Decimal("1") / leverage_cap + TAKER_FEE_RATE
    max_notional = spendable / cost_per_notional
    if qty * price > max_notional:
        return max_notional / price
    return qty


def size_by_risk(
    *,
    equity: Decimal,
    risk_pct: Decimal,
    stop_distance: Decimal,
    price: Decimal,
    leverage_cap: Decimal,
    available_margin: Decimal,
    filters: SymbolFilters,
) -> SizingResult:
    """Size a stop-protected entry: qty = (equity * risk%) / stop_distance.

    Direction-free: the quantity depends on the stop distance, not on the side, so
    long and stop-protected short books share one sizing rule.
    """
    if stop_distance <= 0 or price <= 0 or equity <= 0:
        return SizingResult(
            Decimal("0"), Decimal("0"), Decimal("0"), False, "invalid inputs"
        )
    risk_capital = equity * (risk_pct / Decimal("100"))
    raw_qty = risk_capital / stop_distance
    raw_qty = _leverage_capped_qty(raw_qty, price, equity, leverage_cap)
    raw_qty = margin_capped_qty(raw_qty, price, available_margin, leverage_cap)
    qty = clamp_qty(raw_qty, filters)
    if qty <= 0:
        return SizingResult(
            Decimal("0"), Decimal("0"), Decimal("0"), False, "below min lot or margin"
        )
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
    available_margin: Decimal,
    filters: SymbolFilters,
) -> SizingResult:
    """Size the vol-targeted short sleeve.

    notional = equity * weight% * min(1, vol_target/realized_vol), leverage-capped.
    """
    if price <= 0 or equity <= 0:
        return SizingResult(
            Decimal("0"), Decimal("0"), Decimal("0"), False, "invalid inputs"
        )
    scale = sleeve_scale(vol_target, realized_vol)
    if scale <= 0:
        return SizingResult(
            Decimal("0"), Decimal("0"), Decimal("0"), False, "vol scale zero"
        )
    notional = equity * (weight_pct / Decimal("100")) * scale
    raw_qty = notional / price
    raw_qty = _leverage_capped_qty(raw_qty, price, equity, leverage_cap)
    raw_qty = margin_capped_qty(raw_qty, price, available_margin, leverage_cap)
    qty = clamp_qty(raw_qty, filters)
    if qty <= 0:
        return SizingResult(
            Decimal("0"), Decimal("0"), Decimal("0"), False, "below min lot or margin"
        )
    if not meets_min_notional(qty, price, filters):
        return SizingResult(qty, qty * price, Decimal("0"), False, "below min notional")
    final_notional = qty * price
    return SizingResult(qty, final_notional, final_notional / equity, True, "ok")


def size_long(
    *,
    equity: Decimal,
    risk_pct: Decimal,
    stop_distance: Decimal,
    price: Decimal,
    leverage_cap: Decimal,
    available_margin: Decimal,
    filters: SymbolFilters,
) -> SizingResult:
    """Size a long: qty = (equity * risk%) / stop_distance, leverage-capped."""
    return size_by_risk(
        equity=equity,
        risk_pct=risk_pct,
        stop_distance=stop_distance,
        price=price,
        leverage_cap=leverage_cap,
        available_margin=available_margin,
        filters=filters,
    )
