"""Fail-closed, read-only Binance LIVE account readiness verification."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from app.execution.binance_client import BinanceError

API_RESTRICTIONS_URL = "https://api.binance.com/sapi/v1/account/apiRestrictions"

_UNRELATED_PERMISSION_LABELS = {
    "enableMargin": "margin borrowing",
    "permitsUniversalTransfer": "universal transfers",
    "enableVanillaOptions": "options trading",
    "enableSpotAndMarginTrading": "spot and margin trading",
    "enablePortfolioMarginTrading": "portfolio margin trading",
    "enableFixApiTrade": "FIX trading",
    "enablePredictionTrading": "prediction trading",
}


class SignedBinanceClient(Protocol):
    async def signed_request(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> Any: ...


@dataclass(frozen=True)
class LiveReadiness:
    ip_restricted: bool
    reading_enabled: bool
    futures_enabled: bool
    withdrawals_disabled: bool
    unrelated_permissions_disabled: bool
    one_way_mode: bool
    single_asset_mode: bool
    open_position_count: int
    open_order_count: int
    btcusdt_margin_type: str | None
    btcusdt_leverage: int | None
    issues: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.issues


def _as_list(value: Any, *, endpoint: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise BinanceError(f"unexpected response from {endpoint}")
    return value


def _nonzero_position_count(positions: list[dict[str, Any]]) -> int:
    count = 0
    for position in positions:
        try:
            amount = Decimal(str(position.get("positionAmt", "0")))
        except InvalidOperation as exc:
            raise BinanceError("invalid position amount returned by Binance") from exc
        if amount != 0:
            count += 1
    return count


async def verify_live_readiness(
    client: SignedBinanceClient,
    *,
    required_leverage: int,
    require_flat: bool = True,
) -> LiveReadiness:
    """Read Binance truth and return every blocker without changing account state."""
    permissions = await client.signed_request("GET", API_RESTRICTIONS_URL)
    position_mode = await client.signed_request("GET", "/fapi/v1/positionSide/dual")
    multi_assets = await client.signed_request("GET", "/fapi/v1/multiAssetsMargin")
    positions = _as_list(
        await client.signed_request("GET", "/fapi/v2/positionRisk"),
        endpoint="positionRisk",
    )
    open_orders = _as_list(
        await client.signed_request("GET", "/fapi/v1/openOrders"),
        endpoint="openOrders",
    )
    # Conditional stops are held separately by Binance; a flat account may still
    # have a pending entry or stop on any symbol.
    algo_orders = _as_list(
        await client.signed_request("GET", "/fapi/v1/openAlgoOrders"),
        endpoint="openAlgoOrders",
    )
    if not isinstance(permissions, dict):
        raise BinanceError("unexpected response from apiRestrictions")
    if not isinstance(position_mode, dict) or not isinstance(multi_assets, dict):
        raise BinanceError("unexpected Binance account-mode response")

    ip_restricted = permissions.get("ipRestrict") is True
    reading_enabled = permissions.get("enableReading") is True
    futures_enabled = permissions.get("enableFutures") is True
    withdrawals_disabled = permissions.get("enableWithdrawals") is False
    enabled_unrelated = tuple(
        label
        for field, label in _UNRELATED_PERMISSION_LABELS.items()
        if permissions.get(field) is True
    )
    unrelated_permissions_disabled = not enabled_unrelated
    one_way_mode = position_mode.get("dualSidePosition") is False
    single_asset_mode = multi_assets.get("multiAssetsMargin") is False
    open_position_count = _nonzero_position_count(positions)
    open_order_count = len(open_orders) + len(algo_orders)

    btcusdt = next((row for row in positions if row.get("symbol") == "BTCUSDT"), None)
    margin_type = str(btcusdt.get("marginType")) if btcusdt is not None else None
    try:
        leverage = int(str(btcusdt.get("leverage"))) if btcusdt is not None else None
    except (TypeError, ValueError) as exc:
        raise BinanceError("invalid BTCUSDT leverage returned by Binance") from exc

    issues: list[str] = []
    if not ip_restricted:
        issues.append("API key must be restricted to trusted VPS IPs")
    if not reading_enabled:
        issues.append("API key read access must be enabled")
    if not futures_enabled:
        issues.append("API key Futures trading must be enabled")
    if not withdrawals_disabled:
        issues.append("API withdrawals must be disabled")
    if enabled_unrelated:
        issues.append(f"disable unrelated permissions: {', '.join(enabled_unrelated)}")
    if not one_way_mode:
        issues.append("Binance Futures must use One-way Mode, not Hedge Mode")
    if not single_asset_mode:
        issues.append("Binance Futures must use Single-Asset Mode")
    if require_flat and open_position_count:
        issues.append(f"close or reconcile {open_position_count} existing LIVE positions")
    if require_flat and open_order_count:
        issues.append(f"cancel or reconcile {open_order_count} existing LIVE open orders")
    if margin_type != "isolated":
        issues.append("BTCUSDT margin type must be isolated")
    if leverage != required_leverage:
        issues.append(
            f"BTCUSDT leverage must equal the active strategy setting ({required_leverage}x)"
        )

    return LiveReadiness(
        ip_restricted=ip_restricted,
        reading_enabled=reading_enabled,
        futures_enabled=futures_enabled,
        withdrawals_disabled=withdrawals_disabled,
        unrelated_permissions_disabled=unrelated_permissions_disabled,
        one_way_mode=one_way_mode,
        single_asset_mode=single_asset_mode,
        open_position_count=open_position_count,
        open_order_count=open_order_count,
        btcusdt_margin_type=margin_type,
        btcusdt_leverage=leverage,
        issues=tuple(issues),
    )
