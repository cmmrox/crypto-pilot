"""Production Exchange adapter over BinanceClient (signed endpoints).

Written now against the documented Binance USDT-M futures API; validated live
against DEMO once the API key is configured (Stage 4 live QA). All money Decimal.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.execution.binance_client import BinanceClient
from app.execution.exchange import AccountState, OrderResult, Position
from app.execution.filters import SymbolFilters


class BinanceExchange:
    """Implements the Exchange protocol using signed Binance requests."""

    def __init__(self, client: BinanceClient) -> None:
        self._c = client

    async def get_filters(self, symbol: str) -> SymbolFilters:
        return SymbolFilters.from_exchange(await self._c.get_exchange_filters(symbol))

    async def get_account(self) -> AccountState:
        data = await self._c.signed_request("GET", "/fapi/v2/account")
        positions = [
            Position(
                symbol=p["symbol"],
                qty=Decimal(str(p["positionAmt"])),
                entry_price=Decimal(str(p["entryPrice"])),
            )
            for p in data.get("positions", [])
            if Decimal(str(p["positionAmt"])) != 0
        ]
        return AccountState(
            balance=Decimal(str(data["totalWalletBalance"])),
            available=Decimal(str(data["availableBalance"])),
            unrealized_pnl=Decimal(str(data["totalUnrealizedProfit"])),
            positions=positions,
        )

    async def get_position(self, symbol: str) -> Position:
        data = await self._c.signed_request(
            "GET", "/fapi/v2/positionRisk", {"symbol": symbol}
        )
        row = data[0] if data else {"positionAmt": "0", "entryPrice": "0"}
        return Position(
            symbol=symbol,
            qty=Decimal(str(row["positionAmt"])),
            entry_price=Decimal(str(row["entryPrice"])),
        )

    async def get_open_orders(self, symbol: str) -> list[OrderResult]:
        data = await self._c.signed_request("GET", "/fapi/v1/openOrders", {"symbol": symbol})
        return [self._to_result(o) for o in data]

    async def place_market(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        *,
        client_order_id: str,
        reduce_only: bool = False,
    ) -> OrderResult:
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": _fmt(qty),
            "newClientOrderId": client_order_id,
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        return self._to_result(await self._c.signed_request("POST", "/fapi/v1/order", params))

    async def place_stop_market(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        stop_price: Decimal,
        *,
        client_order_id: str,
        reduce_only: bool = True,
    ) -> OrderResult:
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "STOP_MARKET",
            "quantity": _fmt(qty),
            "stopPrice": _fmt(stop_price),
            "newClientOrderId": client_order_id,
            "reduceOnly": "true" if reduce_only else "false",
            "workingType": "MARK_PRICE",
        }
        return self._to_result(await self._c.signed_request("POST", "/fapi/v1/order", params))

    async def place_take_profit(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        *,
        client_order_id: str,
        reduce_only: bool = True,
    ) -> OrderResult:
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": _fmt(qty),
            "price": _fmt(price),
            "newClientOrderId": client_order_id,
            "reduceOnly": "true" if reduce_only else "false",
        }
        return self._to_result(await self._c.signed_request("POST", "/fapi/v1/order", params))

    async def cancel_all(self, symbol: str) -> int:
        before = await self.get_open_orders(symbol)
        await self._c.signed_request("DELETE", "/fapi/v1/allOpenOrders", {"symbol": symbol})
        return len(before)

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        await self._c.signed_request(
            "POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage}
        )

    @staticmethod
    def _to_result(o: dict[str, Any]) -> OrderResult:
        return OrderResult(
            client_order_id=str(o.get("clientOrderId", "")),
            exchange_order_id=str(o.get("orderId", "")),
            status=str(o.get("status", "NEW")),
            filled_qty=Decimal(str(o.get("executedQty", "0"))),
            avg_price=Decimal(str(o.get("avgPrice", "0") or "0")),
            raw=o,
        )


def _fmt(d: Decimal) -> str:
    """Format a Decimal for Binance (plain string, no exponent)."""
    return format(d.normalize(), "f")
