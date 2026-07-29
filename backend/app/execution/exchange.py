"""Exchange abstraction (dependency inversion at the trading boundary).

The OrderManager, Reconciler and bot loop depend on the `Exchange` protocol, never
on Binance directly. `BinanceExchange` is the production adapter; `FakeExchange`
(tests/fakes) simulates fills deterministically so the whole execution layer is
tested without network or credentials. Real DEMO validation swaps in
`BinanceExchange` once the API key is configured.

All money is Decimal.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from app.execution.filters import SymbolFilters


@dataclass(frozen=True)
class OrderResult:
    """Normalized result of a placed order."""

    client_order_id: str
    exchange_order_id: str
    status: str  # NEW | FILLED | PARTIALLY_FILLED | CANCELED | REJECTED
    filled_qty: Decimal
    avg_price: Decimal
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Fill:
    """One exchange trade fill, including exact fee and realized P&L."""

    exchange_order_id: str
    exchange_trade_id: str
    side: str
    qty: Decimal
    price: Decimal
    commission: Decimal
    realized_pnl: Decimal
    filled_at: dt.datetime


@dataclass(frozen=True)
class FundingIncome:
    """One funding-fee income row attributable to the symbol."""

    exchange_income_id: str
    amount: Decimal
    occurred_at: dt.datetime


@dataclass(frozen=True)
class Position:
    """Current exchange position for a symbol (signed qty: + long, - short)."""

    symbol: str
    qty: Decimal
    entry_price: Decimal


@dataclass(frozen=True)
class AccountState:
    """Snapshot of account truth from the exchange."""

    balance: Decimal
    available: Decimal
    unrealized_pnl: Decimal
    positions: list[Position]


class Exchange(Protocol):
    """The trading surface the engine depends on. Implementations must be idempotent
    on client_order_id (a retried placement must not double-fill)."""

    async def get_filters(self, symbol: str) -> SymbolFilters: ...

    async def get_account(self) -> AccountState: ...

    async def get_position(self, symbol: str) -> Position: ...

    async def get_mark_price(self, symbol: str) -> Decimal: ...

    async def get_open_orders(self, symbol: str) -> list[OrderResult]: ...

    async def get_order(self, symbol: str, client_order_id: str) -> OrderResult: ...

    async def get_order_fills(self, symbol: str, exchange_order_id: str) -> list[Fill]: ...

    async def get_funding_income(
        self, symbol: str, *, start_at: dt.datetime
    ) -> list[FundingIncome]: ...

    async def place_market(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        *,
        client_order_id: str,
        reduce_only: bool = False,
    ) -> OrderResult: ...

    async def place_stop_market(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        stop_price: Decimal,
        *,
        client_order_id: str,
        reduce_only: bool = True,
    ) -> OrderResult: ...

    async def place_take_profit(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        *,
        client_order_id: str,
        reduce_only: bool = True,
    ) -> OrderResult: ...

    async def cancel_all(self, symbol: str) -> int: ...

    async def cancel_order(self, symbol: str, client_order_id: str) -> OrderResult: ...

    async def set_leverage(self, symbol: str, leverage: int) -> None: ...
