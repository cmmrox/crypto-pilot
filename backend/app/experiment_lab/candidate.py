"""Offline adapter for reviewed declarative candidates; never registered automatically."""

from typing import Any

from strategy_runtime.parameters import TrendRiderParameters
from strategy_runtime.trend_rider import TrendRider


def candidate_for_parity(bundle: dict[str, Any]) -> TrendRider:
    if bundle.get("schema_version") != 1 or bundle.get("family") != "trend_rider_v6_4h":
        raise ValueError("Unsupported candidate contract")
    if bundle.get("interval") != "4h" or bundle.get("symbol") != "BTCUSDT":
        raise ValueError("Candidate needs additional production runtime support")
    if bundle.get("activation_allowed") is not False:
        raise ValueError("Research candidates cannot request activation")
    return TrendRider(TrendRiderParameters.from_values(bundle["parameters"]), "4h")
