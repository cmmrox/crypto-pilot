"""Deterministic in-memory Exchange for testing the execution layer without
network or credentials. Simulates immediate MARKET fills and resting stop/TP
orders. Idempotent on client_order_id.
"""

from __future__ import annotations

from decimal import Decimal

from app.execution.exchange import AccountState, OrderResult, Position
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

    async def get_open_orders(self, symbol: str) -> list[OrderResult]:
        return list(self._open_orders.values())

    async def place_market(
        self, symbol, side, qty, *, client_order_id, reduce_only=False
    ) -> OrderResult:
        if client_order_id in self._seen_ids:  # idempotency
            return OrderResult(client_order_id, "DUP", "FILLED", Decimal("0"), self.mark)
        self._seen_ids.add(client_order_id)
        self.placed.append(("MARKET", side, qty))
        signed = qty if side == "BUY" else -qty
        if self._pos == 0:
            self._entry = self.mark
        self._pos += signed
        if self._pos == 0:
            self._entry = Decimal("0")
        return OrderResult(client_order_id, f"F{len(self._seen_ids)}", "FILLED", qty, self.mark)

    async def place_stop_market(
        self, symbol, side, qty, stop_price, *, client_order_id, reduce_only=True
    ) -> OrderResult:
        self.placed.append(("STOP_MARKET", side, qty))
        r = OrderResult(client_order_id, f"S{client_order_id}", "NEW", Decimal("0"), Decimal("0"))
        self._open_orders[client_order_id] = r
        return r

    async def place_take_profit(
        self, symbol, side, qty, price, *, client_order_id, reduce_only=True
    ) -> OrderResult:
        self.placed.append(("LIMIT", side, qty))
        r = OrderResult(client_order_id, f"T{client_order_id}", "NEW", Decimal("0"), Decimal("0"))
        self._open_orders[client_order_id] = r
        return r

    async def cancel_all(self, symbol) -> int:
        n = len(self._open_orders)
        self._open_orders.clear()
        return n

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
