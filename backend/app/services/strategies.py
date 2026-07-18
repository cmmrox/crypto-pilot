"""Strategy metadata service — bridges the pure strategy registry to the API.

Kept in services/ (not strategies/) so the strategy package stays free of API
concerns and the import-boundary contract holds.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.strategies import get_strategy, registered_names

# Static manifest facts (direction, parity) per registered strategy. Parity is
# enforced by the CI parity gate (tests/parity); this flag surfaces that fact.
_MANIFEST: dict[str, dict[str, object]] = {
    "trend_rider_v6": {"direction": "LONG + SHORT", "parity_verified": True},
    "trend_rider_v52": {"direction": "LONG ONLY", "parity_verified": True},
}


@dataclass(frozen=True)
class StrategyInfo:
    name: str
    validated_release: str
    direction: str
    warmup_bars: int
    params: dict[str, float]
    parity_verified: bool


def list_registered() -> list[StrategyInfo]:
    infos = []
    for name in registered_names():
        s = get_strategy(name)
        manifest = _MANIFEST.get(name, {"direction": "UNKNOWN", "parity_verified": False})
        infos.append(
            StrategyInfo(
                name=name,
                validated_release=getattr(s, "validated_release", "—"),
                direction=str(manifest["direction"]),
                warmup_bars=s.warmup_bars(),
                params=dict(s.params),
                parity_verified=bool(manifest["parity_verified"]),
            )
        )
    return infos
