"""Unit tests for the independent monthly circuit breakers (QA-4)."""

from __future__ import annotations

from decimal import Decimal

from app.risk.breakers import evaluate_breaker, is_new_month

D = Decimal


def test_breaker_not_tripped_within_cap() -> None:
    st = evaluate_breaker(month_start_equity=D("10000"), month_to_date_pnl=D("-300"))
    assert not st.tripped  # -3% < -4% cap


def test_breaker_trips_at_cap() -> None:
    st = evaluate_breaker(month_start_equity=D("10000"), month_to_date_pnl=D("-400"))
    assert st.tripped  # exactly -4%
    assert st.drawdown_pct == D("-0.04")


def test_breaker_trips_beyond_cap() -> None:
    st = evaluate_breaker(month_start_equity=D("10000"), month_to_date_pnl=D("-450"))
    assert st.tripped


def test_breaker_positive_pnl_not_tripped() -> None:
    st = evaluate_breaker(month_start_equity=D("10000"), month_to_date_pnl=D("500"))
    assert not st.tripped


def test_breaker_custom_cap() -> None:
    st = evaluate_breaker(
        month_start_equity=D("10000"), month_to_date_pnl=D("-300"), cap=D("0.03")
    )
    assert st.tripped  # -3% hits a 3% cap


def test_breaker_zero_equity_safe() -> None:
    st = evaluate_breaker(month_start_equity=D("0"), month_to_date_pnl=D("-100"))
    assert not st.tripped
    assert st.drawdown_pct == D("0")


def test_new_month_detection() -> None:
    assert is_new_month(None, (2026, 7))
    assert is_new_month((2026, 6), (2026, 7))
    assert not is_new_month((2026, 7), (2026, 7))


def test_breakers_are_independent() -> None:
    # Long tripped, short healthy — evaluated separately, no coupling.
    long_st = evaluate_breaker(month_start_equity=D("10000"), month_to_date_pnl=D("-500"))
    short_st = evaluate_breaker(month_start_equity=D("10000"), month_to_date_pnl=D("100"))
    assert long_st.tripped
    assert not short_st.tripped
