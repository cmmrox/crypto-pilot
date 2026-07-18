"""Bot runtime state — persisted to survive restarts (BSD FR-02).

The bot's desired-running flag and current run id live in app_settings-adjacent
storage so a container restart resumes the prior state and reconciles before acting.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum


class BotStatus(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    SAFE_MODE = "safe_mode"


@dataclass
class BotSnapshot:
    status: BotStatus
    environment: str
    strategy: str
    run_id: int | None
    started_at: dt.datetime | None
    last_tick_at: dt.datetime | None
    safe_mode_reason: str | None = None
