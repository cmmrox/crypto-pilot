"""Selection is deterministic; an LLM cannot award deployability."""

from decimal import Decimal

POLICY_VERSION = "monthly-consistency-v1"


def eligibility(metrics: dict[str, object]) -> list[str]:
    reasons = []
    checks = (
        (
            Decimal(str(metrics["max_drawdown"])) >= Decimal("-0.20"),
            "Drawdown exceeds 20%",
        ),
        (
            Decimal(str(metrics["worst_month"])) >= Decimal("-0.05"),
            "Worst month below -5%",
        ),
        (int(str(metrics["full_months"])) >= 12, "Fewer than 12 complete months"),
        (
            Decimal(str(metrics["profitable_month_ratio"])) >= Decimal("0.70"),
            "Fewer than 70% profitable months",
        ),
        (int(str(metrics["trade_count"])) >= 30, "Fewer than 30 closed trades"),
        (Decimal(str(metrics["net_profit"])) > 0, "Net profit is not positive"),
        (
            Decimal(str(metrics["stressed_net_profit"])) > 0,
            "Not profitable under doubled costs",
        ),
    )
    for passed, reason in checks:
        if not passed:
            reasons.append(reason)
    # Candle studies cannot establish exchange fills or liquidation survival.
    if metrics["fidelity"] != "TRADE_REPLAY":
        reasons.append("Trade-level verification required")
    if int(str(metrics["funding_mark_fallbacks"])):
        reasons.append(
            "Historical funding mark prices are incomplete; candle-open proxies used"
        )
    reasons.extend(
        [
            "Untouched forward validation required",
            "Liquidation and liquidity survival not established",
        ]
    )
    return reasons
