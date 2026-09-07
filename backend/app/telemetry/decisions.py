"""Record closed-candle decisions without a network call to the research service."""

import datetime as dt
import hashlib
import json
from dataclasses import asdict
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Event
from app.strategies.base import Candle, Intent, Strategy, TradeState

log = get_logger("decision_observation")


def record_decision(
    session: AsyncSession,
    *,
    strategy: Strategy,
    candles: list[Candle],
    state: TradeState,
    intents: list[Intent],
    entries_allowed: bool,
    run_id: int,
    equity: Decimal,
    execution_price: Decimal,
) -> None:
    """Queue one DB row in the existing transaction and mirror safe data to logs.

    If the trading transaction rolls back, stdout still identifies the decision;
    the database export explicitly reports that it is committed-event coverage only.
    """
    closed = candles[-1]
    history_hash = hashlib.sha256(
        json.dumps([asdict(row) for row in candles], sort_keys=True).encode()
    ).hexdigest()
    payload = {
        "schema_version": 1,
        "strategy_id": strategy.manifest.strategy_id,
        "release": strategy.manifest.release,
        "interval": strategy.manifest.market.interval,
        "closed_open_time_ms": closed.open_time_ms,
        "history_sha256": history_hash,
        "history_bars": len(candles),
        "last_candle": asdict(closed),
        "equity": str(equity),
        "execution_price": str(execution_price),
        "state": asdict(state),
        "entries_allowed": entries_allowed,
        "intents": [
            {"type": type(intent).__name__, "values": asdict(intent)} for intent in intents
        ],
        "outcome": "NO_SIGNAL"
        if not intents
        else "INTENT_EMITTED"
        if entries_allowed
        else "ENTRY_GATE_CLOSED",
        "run_id": run_id,
    }
    reference = f"decision:{run_id}:{closed.open_time_ms}"
    session.add(
        Event(
            ts=dt.datetime.now(dt.UTC),
            level="INFO",
            category="strategy",
            message="Closed-candle research observation",
            ref=reference,
            payload_json=payload,
        )
    )
    log.info("decision_observed", ref=reference, observation=payload)
