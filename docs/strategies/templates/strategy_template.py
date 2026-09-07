"""Copy to backend/app/strategies/plugins/<valid_name>_<timeframe>.py."""

from __future__ import annotations

from decimal import Decimal

from app.strategies.base import (
    Candle,
    Intent,
    StrategyWatch,
    TradeState,
    register,
)
from app.strategies.manifest import (
    MarketSpec,
    RiskSpec,
    StrategyEducation,
    StrategyManifest,
    ValidationEvidence,
)


class ExampleStrategy:
    manifest = StrategyManifest(
        contract_version=2,
        strategy_id="example_strategy_v1_4h",
        display_name="Example 1 · 4h",  # Follow docs/strategies/NAMING.md.
        release="1.0",
        packaged_default=False,
        direction="LONG ONLY",
        capabilities=("long",),
        market=MarketSpec(
            symbol="BTCUSDT",
            interval="4h",
            decision_point="closed_candle",
            warmup_bars=200,
            history_bars=400,
        ),
        risk=RiskSpec(
            long_risk_pct=Decimal("1"),
            leverage_cap=Decimal("1"),
            long_monthly_loss_cap=Decimal("0.04"),
            short_monthly_loss_cap=Decimal("0.04"),
            short_resize_drift=Decimal("0.20"),
        ),
        education=StrategyEducation(
            summary="One-line owner-facing summary.",
            description="Plain-language explanation of the complete strategy.",
            entries=("Describe each entry rule.",),
            exits=("Describe every exit and position-management rule.",),
            risk_controls=("Describe strategy-owned risk policy.",),
            caveats=("State material limitations.",),
        ),
        validation=ValidationEvidence(
            method="chronological runtime-equivalent replay",
            status="verified",
            reference="docs/qa/reports/REPLACE-ME.md",
        ),
    )

    def __init__(self) -> None:
        self.params: dict[str, float] = {}

    def on_candle(self, candles: list[Candle], state: TradeState) -> list[Intent]:
        del candles, state
        return []

    def inspect(self, candles: list[Candle]) -> StrategyWatch | None:
        del candles
        return None


PLUGIN = register(ExampleStrategy())
