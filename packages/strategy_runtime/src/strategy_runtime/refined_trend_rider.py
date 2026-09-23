"""Pinned refined 4h release, sharing every decision rule with Trend Rider v6.

This is an operator-selectable release, not a change to the packaged default.
The sole parameter change from v6 is the long runner's 4.5 ATR trail.
"""

from dataclasses import replace

from strategy_runtime.manifest import ValidationEvidence
from strategy_runtime.parameters import TrendRiderParameters
from strategy_runtime.trend_rider import TrendRider


class RefinedTrendRider(TrendRider):
    """No editable constructor: research parameters must ship as new releases."""

    manifest = replace(
        TrendRider.manifest,
        strategy_id="trend_rider_refined_v1_4h",
        display_name="Atlas 6 Trail · 4h",
        release="1.0",
        packaged_default=False,
        legacy_ids=(),
        education=replace(
            TrendRider.manifest.education,
            summary="Trend Rider v6 with a wider 4.5 ATR long trailing stop.",
            description=(
                "The refined four-hour release changes only the long runner trail "
                "from 4 to 4.5 ATR. Entries, initial stop, partial profit, sizing and "
                "the stop-free short sleeve remain unchanged. Selection does not "
                "start the bot or change DEMO/LIVE mode."
            ),
            exits=(
                "Longs take 40% at 1R; after TP1, ratchet the stop to the maximum "
                "of its prior level, breakeven, and highest high minus 4.5 ATR.",
                "Longs also exit when the bull regime ends.",
                "Shorts cover when the deep-bear condition ends; no short price stop.",
            ),
            caveats=(
                *TrendRider.manifest.education.caveats,
                "Aggressive profile: 15% long risk and up to 6x leverage. Monthly "
                "breakers do not guarantee a four-percent maximum loss.",
                "Historical candle replay improved three-year profit, but had a "
                "worse final-year loss and worst month than the original settings.",
                "Parity verifies software behavior, not live profitability or "
                "identical fills. Slippage, latency, liquidity and liquidation differ.",
            ),
        ),
        validation=ValidationEvidence(
            method="pinned-parameter parity, closed-candle replay and bot integration",
            status="verified",
            reference="docs/qa/reports/REFINED-4H-RELEASE-2026-09-06.md",
        ),
    )

    def __init__(self) -> None:
        super().__init__(TrendRiderParameters(trail_atr=4.5), interval="4h")
