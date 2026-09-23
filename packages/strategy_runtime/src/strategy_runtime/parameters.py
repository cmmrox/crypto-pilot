"""Typed parameter definitions: one source for validation, UI and effective behavior."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class ParameterDefinition:
    key: str
    label: str
    unit: str
    default: str
    minimum: str
    maximum: str
    step: str
    consumer: str


DEFINITIONS = (
    ParameterDefinition("stop_atr", "Long stop distance", "ATR", "2.5", "0.5", "6", "0.1", "entry"),
    ParameterDefinition("tp1_r", "First profit target", "R", "1", "0.5", "5", "0.1", "entry"),
    ParameterDefinition(
        "tp1_frac",
        "Partial close fraction",
        "fraction",
        "0.4",
        "0.1",
        "0.9",
        "0.05",
        "fills",
    ),
    ParameterDefinition(
        "trail_atr", "Long trailing distance", "ATR", "4", "1", "8", "0.1", "management"
    ),
    ParameterDefinition(
        "sleeve_depth_atr",
        "Short regime depth",
        "ATR",
        "0.5",
        "0",
        "3",
        "0.1",
        "regime",
    ),
    ParameterDefinition(
        "sleeve_vol_target",
        "Short volatility target",
        "fraction",
        "0.4",
        "0.1",
        "1",
        "0.05",
        "exposure",
    ),
    ParameterDefinition(
        "sleeve_weight",
        "Short sleeve weight",
        "fraction",
        "0.75",
        "0.1",
        "1",
        "0.05",
        "exposure",
    ),
    ParameterDefinition(
        "sleeve_vol_span",
        "Volatility lookback",
        "bars",
        "48",
        "12",
        "120",
        "1",
        "volatility",
    ),
    ParameterDefinition("fast_period", "Pullback EMA", "bars", "20", "5", "50", "1", "indicators"),
    ParameterDefinition(
        "medium_period", "Regime EMA", "bars", "50", "20", "100", "1", "indicators"
    ),
    ParameterDefinition(
        "slow_period",
        "Slow EMA and SMA",
        "bars",
        "200",
        "100",
        "300",
        "1",
        "indicators",
    ),
    ParameterDefinition("atr_period", "ATR lookback", "bars", "14", "5", "40", "1", "indicators"),
    ParameterDefinition("risk_pct", "Long risk", "percent", "15", "0.5", "15", "0.5", "sizing"),
    ParameterDefinition(
        "leverage_cap", "Leverage ceiling", "multiple", "6", "1", "6", "1", "sizing"
    ),
    ParameterDefinition(
        "long_month_cap",
        "Long monthly breaker",
        "fraction",
        "0.04",
        "0.01",
        "0.1",
        "0.01",
        "risk",
    ),
    ParameterDefinition(
        "sleeve_month_cap",
        "Short monthly breaker",
        "fraction",
        "0.04",
        "0.01",
        "0.1",
        "0.01",
        "risk",
    ),
)
INTERVAL_MINUTES = {"30m": 30, "1h": 60, "4h": 240}


def validate_parameters(values: Mapping[str, object]) -> dict[str, str]:
    """Reject unknown, nonfinite, off-grid and inconsistent inputs; fill defaults."""
    known = {item.key for item in DEFINITIONS}
    if set(values) - known:
        raise ValueError("Unknown parameters: " + ", ".join(sorted(set(values) - known)))
    result: dict[str, str] = {}
    for item in DEFINITIONS:
        raw = values.get(item.key, item.default)
        if isinstance(raw, bool):
            raise ValueError(f"{item.key} must be numeric")
        try:
            value = Decimal(str(raw))
        except InvalidOperation as error:
            raise ValueError(f"{item.key} must be numeric") from error
        if not value.is_finite():
            raise ValueError(f"{item.key} must be finite")
        if not Decimal(item.minimum) <= value <= Decimal(item.maximum):
            raise ValueError(f"{item.key} is outside its allowed range")
        if (value - Decimal(item.minimum)) % Decimal(item.step) != 0:
            raise ValueError(f"{item.key} does not match its allowed step")
        result[item.key] = format(value.normalize(), "f")
    if (
        not Decimal(result["fast_period"])
        < Decimal(result["medium_period"])
        < Decimal(result["slow_period"])
    ):
        raise ValueError("EMA periods must satisfy fast < medium < slow")
    return result


@dataclass(frozen=True)
class TrendRiderParameters:
    stop_atr: float = 2.5
    tp1_r: float = 1.0
    tp1_frac: float = 0.4
    trail_atr: float = 4.0
    sleeve_depth_atr: float = 0.5
    sleeve_vol_target: float = 0.4
    sleeve_weight: float = 0.75
    sleeve_vol_span: int = 48
    fast_period: int = 20
    medium_period: int = 50
    slow_period: int = 200
    atr_period: int = 14
    risk_pct: float = 15.0
    leverage_cap: float = 6.0
    long_month_cap: float = 0.04
    sleeve_month_cap: float = 0.04

    @classmethod
    def from_values(cls, values: Mapping[str, object]) -> TrendRiderParameters:
        normalized = validate_parameters(values)
        integers = {
            "sleeve_vol_span",
            "fast_period",
            "medium_period",
            "slow_period",
            "atr_period",
        }
        return cls(
            **{
                item.name: int(normalized[item.name])
                if item.name in integers
                else float(normalized[item.name])
                for item in fields(cls)
            }
        )

    def values(self) -> dict[str, float]:
        return {key: float(value) for key, value in asdict(self).items()}
