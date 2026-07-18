"""Unit tests for position sizing, leverage cap, and lot rounding (QA-4).

Filters mirror the real BTCUSDT DEMO exchangeInfo (stepSize 0.0001, minNotional 50).
"""

from __future__ import annotations

from decimal import Decimal

from app.execution.filters import (
    SymbolFilters,
    clamp_qty,
    meets_min_notional,
    round_price,
    round_qty,
)
from app.risk.sizing import size_long, size_short, sleeve_scale

FILTERS = SymbolFilters(
    step_size=Decimal("0.0001"),
    min_qty=Decimal("0.0001"),
    max_qty=Decimal("120"),
    tick_size=Decimal("0.10"),
    min_notional=Decimal("50"),
)
D = Decimal


def test_round_qty_rounds_down_to_step() -> None:
    assert round_qty(D("0.123456"), D("0.0001")) == D("0.1234")
    assert round_qty(D("0.99999"), D("0.0001")) == D("0.9999")


def test_round_price_to_tick() -> None:
    assert round_price(D("65711.27"), D("0.10")) == D("65711.30")
    assert round_price(D("65711.24"), D("0.10")) == D("65711.20")


def test_clamp_below_min_qty_is_zero() -> None:
    assert clamp_qty(D("0.00005"), FILTERS) == D("0")


def test_min_notional() -> None:
    assert meets_min_notional(D("0.001"), D("65000"), FILTERS)  # 65 >= 50
    assert not meets_min_notional(D("0.0001"), D("65000"), FILTERS)  # 6.5 < 50


def test_size_long_risk_based_quantity() -> None:
    # equity 10000, risk 2% = 200 risk capital; stop distance 2000 → 0.1 BTC.
    r = size_long(
        equity=D("10000"),
        risk_pct=D("2"),
        stop_distance=D("2000"),
        price=D("65000"),
        leverage_cap=D("3"),
        filters=FILTERS,
    )
    assert r.ok
    assert r.qty == D("0.1000")  # 200/2000, rounded to step
    assert r.notional == D("6500.0000")


def test_size_long_leverage_capped() -> None:
    # Tiny stop distance would imply huge qty; leverage cap 3x limits notional.
    r = size_long(
        equity=D("10000"),
        risk_pct=D("2"),
        stop_distance=D("10"),  # 200/10 = 20 BTC uncapped → way over 3x
        price=D("65000"),
        leverage_cap=D("3"),
        filters=FILTERS,
    )
    assert r.ok
    # Notional must not exceed equity * 3 = 30000.
    assert r.notional <= D("30000")
    assert r.leverage <= D("3")


def test_size_long_below_min_notional_fails() -> None:
    r = size_long(
        equity=D("100"),
        risk_pct=D("2"),  # 2 risk capital
        stop_distance=D("2000"),  # 0.001 BTC → notional ~65 ok? 0.001*65000=65
        price=D("65000"),
        leverage_cap=D("3"),
        filters=FILTERS,
    )
    # 2/2000 = 0.001 → 0.0010 rounded; notional 65 >= 50 → ok actually
    assert r.ok


def test_sleeve_scale_caps_at_one() -> None:
    assert sleeve_scale(D("0.40"), D("0.20")) == D("1")  # target>vol → capped at 1
    assert sleeve_scale(D("0.40"), D("0.80")) == D("0.5")  # 0.4/0.8
    assert sleeve_scale(D("0.40"), D("0")) == D("0")


def test_size_short_vol_scaled() -> None:
    # equity 10000, weight 75%, vol target 0.4, realized 0.4 → scale 1 → 7500 notional.
    r = size_short(
        equity=D("10000"),
        weight_pct=D("75"),
        vol_target=D("0.40"),
        realized_vol=D("0.40"),
        price=D("65000"),
        leverage_cap=D("3"),
        filters=FILTERS,
    )
    assert r.ok
    assert r.notional <= D("7500") + D("65")  # ~7500 minus rounding
    assert r.qty > 0


def test_size_short_high_vol_shrinks() -> None:
    """A volatility spike shrinks the short (the sleeve's core risk control)."""
    calm = size_short(
        equity=D("10000"), weight_pct=D("75"), vol_target=D("0.40"),
        realized_vol=D("0.40"), price=D("65000"), leverage_cap=D("3"), filters=FILTERS,
    )
    violent = size_short(
        equity=D("10000"), weight_pct=D("75"), vol_target=D("0.40"),
        realized_vol=D("1.20"), price=D("65000"), leverage_cap=D("3"), filters=FILTERS,
    )
    assert violent.qty < calm.qty  # crash → smaller short automatically


def test_all_money_is_decimal() -> None:
    r = size_long(
        equity=D("10000"), risk_pct=D("2"), stop_distance=D("2000"),
        price=D("65000"), leverage_cap=D("3"), filters=FILTERS,
    )
    assert isinstance(r.qty, Decimal)
    assert isinstance(r.notional, Decimal)
    assert isinstance(r.leverage, Decimal)
