"""Reconciliation: compare expected vs actual exchange state (BSD §8).

On every start and every 4h close the engine compares the position/orders it
expects against the exchange (the source of truth). Any mismatch → safe mode
(no new entries) + event/SMS. Decimal math with a tiny tolerance for dust.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.execution.exchange import Exchange

DUST = Decimal("0.00001")  # ignore sub-lot dust differences


@dataclass(frozen=True)
class ReconcileResult:
    matched: bool
    expected_qty: Decimal
    actual_qty: Decimal
    detail: str


async def reconcile_position(
    exchange: Exchange, symbol: str, expected_qty: Decimal
) -> ReconcileResult:
    """Compare the expected signed position against the exchange.

    expected_qty: signed (+ long, - short, 0 flat) quantity the bot believes it holds.
    """
    pos = await exchange.get_position(symbol)
    diff = abs(pos.qty - expected_qty)
    if diff <= DUST:
        return ReconcileResult(True, expected_qty, pos.qty, "position matches exchange")
    return ReconcileResult(
        False,
        expected_qty,
        pos.qty,
        f"position mismatch: expected {expected_qty}, exchange has {pos.qty}",
    )
