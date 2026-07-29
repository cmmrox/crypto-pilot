"""Production Exchange adapter over BinanceClient (signed endpoints).

Written now against the documented Binance USDT-M futures API; validated live
against DEMO once the API key is configured (Stage 4 live QA). All money Decimal.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import replace
from decimal import Decimal
from typing import Any

from app.execution.binance_client import (
    AmbiguousMutationError,
    BinanceClient,
    BinanceError,
)
from app.execution.exchange import (
    AccountState,
    Fill,
    FundingIncome,
    OrderResult,
    Position,
)
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
        data = await self._c.signed_request("GET", "/fapi/v2/positionRisk", {"symbol": symbol})
        if not isinstance(data, list) or len(data) != 1:
            raise BinanceError(
                f"unexpected position response for {symbol}: expected exactly one row"
            )
        row = data[0]
        if not isinstance(row, dict) or row.get("symbol") != symbol:
            raise BinanceError(f"position response symbol mismatch for {symbol}")
        return Position(
            symbol=symbol,
            qty=Decimal(str(row["positionAmt"])),
            entry_price=Decimal(str(row["entryPrice"])),
        )

    async def get_mark_price(self, symbol: str) -> Decimal:
        return (await self._c.get_mark_price(symbol)).price

    async def get_open_orders(self, symbol: str) -> list[OrderResult]:
        regular = await self._c.signed_request("GET", "/fapi/v1/openOrders", {"symbol": symbol})
        algo = await self._c.signed_request("GET", "/fapi/v1/openAlgoOrders", {"symbol": symbol})
        return [self._to_result(o) for o in regular] + [self._to_algo_result(o) for o in algo]

    async def get_order(self, symbol: str, client_order_id: str) -> OrderResult:
        last_error: BinanceError | None = None
        for attempt in range(3):
            try:
                data = await self._c.signed_request(
                    "GET",
                    "/fapi/v1/order",
                    {"symbol": symbol, "origClientOrderId": client_order_id},
                )
                return self._to_result(data, expected_client_order_id=client_order_id)
            except BinanceError as regular_error:
                if regular_error.code not in {-2011, -2013}:
                    raise
                try:
                    return await self._get_algo_order(symbol, client_order_id)
                except BinanceError as algo_error:
                    if algo_error.code not in {-2011, -2013}:
                        raise
                    last_error = algo_error
            if attempt < 2:
                await asyncio.sleep(0.05 * (2**attempt))
        assert last_error is not None
        raise last_error

    async def get_order_fills(self, symbol: str, exchange_order_id: str) -> list[Fill]:
        data = await self._c.signed_request(
            "GET",
            "/fapi/v1/userTrades",
            {"symbol": symbol, "orderId": exchange_order_id},
        )
        return [
            Fill(
                exchange_order_id=str(row["orderId"]),
                exchange_trade_id=str(row["id"]),
                side=str(row["side"]),
                qty=Decimal(str(row["qty"])),
                price=Decimal(str(row["price"])),
                commission=Decimal(str(row["commission"])),
                realized_pnl=Decimal(str(row["realizedPnl"])),
                filled_at=dt.datetime.fromtimestamp(int(row["time"]) / 1000, tz=dt.UTC),
            )
            for row in data
        ]

    async def get_funding_income(
        self, symbol: str, *, start_at: dt.datetime
    ) -> list[FundingIncome]:
        data = await self._c.signed_request(
            "GET",
            "/fapi/v1/income",
            {
                "symbol": symbol,
                "incomeType": "FUNDING_FEE",
                "startTime": int(start_at.timestamp() * 1000),
                "limit": 1000,
            },
        )
        return [
            FundingIncome(
                exchange_income_id=str(row.get("tranId", "")),
                amount=Decimal(str(row["income"])),
                occurred_at=dt.datetime.fromtimestamp(int(row["time"]) / 1000, tz=dt.UTC),
            )
            for row in data
        ]

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
            # Binance defaults to ACK, which can report zero fill/price for a
            # completed MARKET order. RESULT returns the final FILLED response.
            "newOrderRespType": "RESULT",
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        try:
            data = await self._c.signed_request("POST", "/fapi/v1/order", params)
            result = self._to_result(data, expected_client_order_id=client_order_id)
        except AmbiguousMutationError as exc:
            result = await self._recover_ambiguous_order(
                symbol,
                client_order_id,
                cause=exc,
            )
        if result.status == "FILLED" and result.filled_qty > 0 and result.avg_price <= 0:
            result = await self._resolve_market_avg_price(symbol, result)
        return result

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
            "algoType": "CONDITIONAL",
            "symbol": symbol,
            "side": side,
            "type": "STOP_MARKET",
            "quantity": _fmt(qty),
            "triggerPrice": _fmt(stop_price),
            "clientAlgoId": client_order_id,
            "reduceOnly": "true" if reduce_only else "false",
            "workingType": "MARK_PRICE",
        }
        try:
            data = await self._c.signed_request("POST", "/fapi/v1/algoOrder", params)
            return self._to_algo_result(data, expected_client_order_id=client_order_id)
        except AmbiguousMutationError as exc:
            return await self._recover_ambiguous_order(
                symbol,
                client_order_id,
                cause=exc,
            )

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
        try:
            data = await self._c.signed_request("POST", "/fapi/v1/order", params)
            return self._to_result(data, expected_client_order_id=client_order_id)
        except AmbiguousMutationError as exc:
            return await self._recover_ambiguous_order(
                symbol,
                client_order_id,
                cause=exc,
            )

    async def cancel_all(self, symbol: str) -> int:
        before = await self.get_open_orders(symbol)
        await self._c.signed_request("DELETE", "/fapi/v1/allOpenOrders", {"symbol": symbol})
        await self._c.signed_request("DELETE", "/fapi/v1/algoOpenOrders", {"symbol": symbol})
        return len(before)

    async def cancel_order(self, symbol: str, client_order_id: str) -> OrderResult:
        try:
            data = await self._c.signed_request(
                "DELETE",
                "/fapi/v1/order",
                {"symbol": symbol, "origClientOrderId": client_order_id},
            )
        except BinanceError as regular_error:
            if regular_error.code not in {-2011, -2013}:
                raise
            data = await self._c.signed_request(
                "DELETE",
                "/fapi/v1/algoOrder",
                {"symbol": symbol, "clientAlgoId": client_order_id},
            )
            if str(data.get("code")) != "200":
                raise BinanceError("algo cancellation was not confirmed") from regular_error
            return OrderResult(
                client_order_id=client_order_id,
                exchange_order_id=str(data["algoId"]),
                status="CANCELED",
                filled_qty=Decimal("0"),
                avg_price=Decimal("0"),
                raw=data,
            )
        return self._to_result(data, expected_client_order_id=client_order_id)

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        await self._c.signed_request(
            "POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage}
        )

    async def _recover_ambiguous_order(
        self,
        symbol: str,
        client_order_id: str,
        *,
        cause: AmbiguousMutationError,
    ) -> OrderResult:
        """Resolve an uncertain placement from Binance using its idempotent ID.

        Binance's matching engine and query replicas are eventually consistent.
        Query a bounded number of times; if the order is still not visible, preserve
        the ambiguous error so the bot's failure boundary can flatten any exposure.
        """
        for attempt in range(4):
            try:
                return await self.get_order(symbol, client_order_id)
            except BinanceError as exc:
                if exc.code not in {-2011, -2013}:
                    raise
            if attempt < 3:
                await asyncio.sleep(0.1 * (2**attempt))
        raise cause

    async def _resolve_market_avg_price(self, symbol: str, result: OrderResult) -> OrderResult:
        """Recover a zero RESULT avgPrice from order truth or account trades.

        Binance DEMO can return a fully filled MARKET order with ``avgPrice=0``.
        The bot must not persist that sentinel as an execution price.
        """
        queried = await self.get_order(symbol, result.client_order_id)
        if queried.avg_price > 0:
            return replace(
                result,
                avg_price=queried.avg_price,
                raw={**result.raw, "price_source": "query_order"},
            )
        fills = await self.get_order_fills(symbol, result.exchange_order_id)
        filled_qty = sum((fill.qty for fill in fills), Decimal("0"))
        if filled_qty == result.filled_qty and filled_qty > 0:
            weighted_price = (
                sum((fill.price * fill.qty for fill in fills), Decimal("0")) / filled_qty
            )
            return replace(
                result,
                avg_price=weighted_price,
                raw={**result.raw, "price_source": "account_trades"},
            )
        return result

    async def _get_algo_order(self, symbol: str, client_order_id: str) -> OrderResult:
        data = await self._c.signed_request(
            "GET",
            "/fapi/v1/algoOrder",
            {"symbol": symbol, "clientAlgoId": client_order_id},
        )
        actual_order_id = str(data.get("actualOrderId", ""))
        if actual_order_id:
            actual = self._to_result(
                await self._c.signed_request(
                    "GET",
                    "/fapi/v1/order",
                    {"symbol": symbol, "orderId": actual_order_id},
                )
            )
            return replace(
                actual,
                client_order_id=client_order_id,
                raw={**data, "actual_order": actual.raw},
            )
        return self._to_algo_result(data, expected_client_order_id=client_order_id)

    @staticmethod
    def _to_result(
        o: dict[str, Any], *, expected_client_order_id: str | None = None
    ) -> OrderResult:
        if not isinstance(o, dict):
            raise BinanceError("invalid order response shape")
        client_order_id = str(o.get("clientOrderId", ""))
        exchange_order_id = str(o.get("orderId", ""))
        status = str(o.get("status", ""))
        if not client_order_id or not exchange_order_id:
            raise BinanceError("order response missing identity")
        if expected_client_order_id is not None and client_order_id != expected_client_order_id:
            raise BinanceError("order response client identity mismatch")
        if status not in {
            "NEW",
            "PARTIALLY_FILLED",
            "FILLED",
            "CANCELED",
            "REJECTED",
            "EXPIRED",
        }:
            raise BinanceError("order response has invalid status")
        filled_qty = Decimal(str(o.get("executedQty", "0")))
        if filled_qty < 0:
            raise BinanceError("order response has negative filled quantity")
        return OrderResult(
            client_order_id=client_order_id,
            exchange_order_id=exchange_order_id,
            status=status,
            filled_qty=filled_qty,
            avg_price=Decimal(str(o.get("avgPrice", "0") or "0")),
            raw=o,
        )

    @staticmethod
    def _to_algo_result(
        o: dict[str, Any], *, expected_client_order_id: str | None = None
    ) -> OrderResult:
        if not isinstance(o, dict):
            raise BinanceError("invalid algo order response shape")
        client_order_id = str(o.get("clientAlgoId", ""))
        exchange_order_id = str(o.get("algoId", ""))
        algo_status = str(o.get("algoStatus", ""))
        if not client_order_id or not exchange_order_id:
            raise BinanceError("algo order response missing identity")
        if expected_client_order_id is not None and client_order_id != expected_client_order_id:
            raise BinanceError("algo order response client identity mismatch")
        status_map = {
            "NEW": "NEW",
            "CANCELED": "CANCELED",
            "REJECTED": "REJECTED",
            "EXPIRED": "EXPIRED",
        }
        if algo_status not in status_map:
            raise BinanceError(f"algo order response has invalid status: {algo_status}")
        return OrderResult(
            client_order_id=client_order_id,
            exchange_order_id=exchange_order_id,
            status=status_map[algo_status],
            filled_qty=Decimal("0"),
            avg_price=Decimal("0"),
            raw=o,
        )


def _fmt(d: Decimal) -> str:
    """Format a Decimal for Binance (plain string, no exponent)."""
    return format(d.normalize(), "f")
