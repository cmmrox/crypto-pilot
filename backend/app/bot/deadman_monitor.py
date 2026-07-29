"""Independent health monitor for the in-process ingest scheduler."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.request

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import get_sessionmaker
from app.services.events import record_event
from app.services.notify_config import notify_event

_log = get_logger("deadman_monitor")


def _healthy(url: str, timeout: float) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.load(response)
        return response.status == 200 and payload.get("status") == "ok"
    except Exception:
        return False


async def _alert(*, recovered: bool, failures: int) -> None:
    async with get_sessionmaker()() as session:
        message = (
            "Independent deadman monitor recovered"
            if recovered
            else "Independent deadman monitor detected unhealthy backend"
        )
        await record_event(
            session,
            level="INFO" if recovered else "ERROR",
            category="system",
            message=message,
            ref="deadman:backend",
            payload={"consecutive_failures": failures},
        )
        if not recovered:
            await notify_event(
                session,
                kind="error",
                payload={"message": message, "failures": failures},
            )
        await session.commit()


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    url = os.getenv("CP_DEADMAN_URL", "http://backend:8000/health/deep")
    interval = float(os.getenv("CP_DEADMAN_INTERVAL_SECONDS", "60"))
    threshold = int(os.getenv("CP_DEADMAN_FAILURE_THRESHOLD", "3"))
    timeout = float(os.getenv("CP_DEADMAN_TIMEOUT_SECONDS", "10"))
    failures = 0
    alerted = False
    while True:
        healthy = await asyncio.to_thread(_healthy, url, timeout)
        if healthy:
            if alerted:
                await _alert(recovered=True, failures=failures)
            failures = 0
            alerted = False
        else:
            failures += 1
            if failures >= threshold and not alerted:
                await _alert(recovered=False, failures=failures)
                alerted = True
        _log.info("deadman_check", healthy=healthy, consecutive_failures=failures)
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(run())
