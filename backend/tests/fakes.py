"""Deterministic in-memory Exchange for testing the execution layer without
network or credentials. Simulates immediate MARKET fills and resting stop/TP
orders. Idempotent on client_order_id.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.execution.exchange import (
    AccountState,
    Fill,
    FundingIncome,
    OrderResult,
    Position,
)
from app.execution.filters import SymbolFilters

_BTC_FILTERS = SymbolFilters(
    step_size=Decimal("0.0001"),
    min_qty=Decimal("0.0001"),
    max_qty=Decimal("120"),
    tick_size=Decimal("0.10"),
    min_notional=Decimal("50"),
)


class FakeExchange:
    """Implements the Exchange protocol in memory."""

    def __init__(
        self, *, mark_price: Decimal = Decimal("65000"), balance: Decimal = Decimal("10000")
    ) -> None:
        self.mark = mark_price
        self._balance = balance
        self._pos = Decimal("0")
        self._entry = Decimal("0")
        self._open_orders: dict[str, OrderResult] = {}
        self._orders: dict[str, OrderResult] = {}
        self._fills: dict[str, list[Fill]] = {}
        self._funding: list[FundingIncome] = []
        self._resting: dict[str, tuple[str, Decimal]] = {}
        self._seen_ids: set[str] = set()
        self.leverage: int | None = None
        self.placed: list[tuple[str, str, Decimal]] = []  # (type, side, qty) log

    async def get_filters(self, symbol: str) -> SymbolFilters:
        return _BTC_FILTERS

    async def get_account(self) -> AccountState:
        upnl = (self.mark - self._entry) * self._pos if self._pos != 0 else Decimal("0")
        positions = [Position("BTCUSDT", self._pos, self._entry)] if self._pos != 0 else []
        return AccountState(self._balance, self._balance, upnl, positions)

    async def get_position(self, symbol: str) -> Position:
        return Position(symbol, self._pos, self._entry)

    async def get_mark_price(self, symbol: str) -> Decimal:
        return self.mark

    async def get_open_orders(self, symbol: str) -> list[OrderResult]:
        return list(self._open_orders.values())

    async def get_order(self, symbol: str, client_order_id: str) -> OrderResult:
        return self._orders[client_order_id]

    async def get_order_fills(self, symbol: str, exchange_order_id: str) -> list[Fill]:
        return list(self._fills.get(exchange_order_id, []))

    async def get_funding_income(
        self, symbol: str, *, start_at: dt.datetime
    ) -> list[FundingIncome]:
        return [row for row in self._funding if row.occurred_at >= start_at]

    async def place_market(
        self, symbol, side, qty, *, client_order_id, reduce_only=False
    ) -> OrderResult:
        if client_order_id in self._seen_ids:  # idempotency
            return OrderResult(client_order_id, "DUP", "FILLED", Decimal("0"), self.mark)
        self._seen_ids.add(client_order_id)
        self.placed.append(("MARKET", side, qty))
        previous_entry = self._entry
        signed = qty if side == "BUY" else -qty
        if self._pos == 0:
            self._entry = self.mark
        self._pos += signed
        if self._pos == 0:
            self._entry = Decimal("0")
        order_id = f"F{len(self._seen_ids)}"
        result = OrderResult(client_order_id, order_id, "FILLED", qty, self.mark)
        self._orders[client_order_id] = result
        realized = Decimal("0")
        if reduce_only:
            if side == "SELL":
                realized = (self.mark - previous_entry) * qty
            else:
                realized = (previous_entry - self.mark) * qty
        self._fills[order_id] = [
            Fill(
                exchange_order_id=order_id,
                exchange_trade_id=f"TF{len(self._seen_ids)}",
                side=side,
                qty=qty,
                price=self.mark,
                commission=qty * self.mark * Decimal("0.0004"),
                realized_pnl=realized,
                filled_at=dt.datetime.now(dt.UTC),
            )
        ]
        return result

    async def place_stop_market(
        self, symbol, side, qty, stop_price, *, client_order_id, reduce_only=True
    ) -> OrderResult:
        self.placed.append(("STOP_MARKET", side, qty))
        r = OrderResult(client_order_id, f"S{client_order_id}", "NEW", Decimal("0"), Decimal("0"))
        self._open_orders[client_order_id] = r
        self._orders[client_order_id] = r
        self._resting[client_order_id] = (side, qty)
        return r

    async def place_take_profit(
        self, symbol, side, qty, price, *, client_order_id, reduce_only=True
    ) -> OrderResult:
        self.placed.append(("LIMIT", side, qty))
        r = OrderResult(client_order_id, f"T{client_order_id}", "NEW", Decimal("0"), Decimal("0"))
        self._open_orders[client_order_id] = r
        self._orders[client_order_id] = r
        self._resting[client_order_id] = (side, qty)
        return r

    async def cancel_all(self, symbol) -> int:
        n = len(self._open_orders)
        for client_order_id, row in self._open_orders.items():
            self._orders[client_order_id] = OrderResult(
                row.client_order_id,
                row.exchange_order_id,
                "CANCELED",
                row.filled_qty,
                row.avg_price,
                row.raw,
            )
        self._open_orders.clear()
        self._resting.clear()
        return n

    async def cancel_order(self, symbol: str, client_order_id: str) -> OrderResult:
        row = self._open_orders.pop(client_order_id)
        cancelled = OrderResult(
            row.client_order_id,
            row.exchange_order_id,
            "CANCELED",
            row.filled_qty,
            row.avg_price,
            row.raw,
        )
        self._orders[client_order_id] = cancelled
        self._resting.pop(client_order_id, None)
        return cancelled

    def fill_resting(self, client_order_id: str, *, price: Decimal) -> None:
        """Simulate an exchange-side stop/TP fill between candle decisions."""
        row = self._open_orders.pop(client_order_id)
        side, qty = self._resting.pop(client_order_id)
        previous_entry = self._entry
        signed = qty if side == "BUY" else -qty
        self._pos += signed
        if self._pos == 0:
            self._entry = Decimal("0")
        filled = OrderResult(
            row.client_order_id,
            row.exchange_order_id,
            "FILLED",
            qty,
            price,
        )
        self._orders[client_order_id] = filled
        realized = (
            (price - previous_entry) * qty if side == "SELL" else (previous_entry - price) * qty
        )
        self._fills[row.exchange_order_id] = [
            Fill(
                exchange_order_id=row.exchange_order_id,
                exchange_trade_id=f"TR{len(self._fills) + 1}",
                side=side,
                qty=qty,
                price=price,
                commission=qty * price * Decimal("0.0004"),
                realized_pnl=realized,
                filled_at=dt.datetime.now(dt.UTC),
            )
        ]

    async def set_leverage(self, symbol, leverage) -> None:
        self.leverage = leverage


class FakeSmsGateway:
    """In-memory SMS gateway. `fail_times` first sends fail, then succeed."""

    def __init__(self, *, fail_times: int = 0, always_fail: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self._fail_times = fail_times
        self._always_fail = always_fail
        self.attempts = 0

    async def send(self, to: str, message: str):  # type: ignore[no-untyped-def]
        from app.notifier.gateway import SmsResult

        self.attempts += 1
        if self._always_fail or self.attempts <= self._fail_times:
            return SmsResult(False, "simulated failure")
        self.sent.append((to, message))
        return SmsResult(True, "delivered")


class FakeSummaryProvider:
    """Deterministic summary provider for testing the news pipeline."""

    def __init__(self, sentiment: str = "Neutral-positive") -> None:
        self._sentiment = sentiment

    async def summarize(self, items):  # type: ignore[no-untyped-def]
        from app.news.provider import Briefing

        bullets = [{"text": f"Summary of {i['title']}", "source": i["source"]} for i in items[:5]]
        if not bullets:
            bullets = [{"text": "No items", "source": ""}]
        return Briefing(self._sentiment, bullets, "gpt-5.5")
