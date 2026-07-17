"""Structured JSON logging (structlog) per docs/guidelines/LOGGING_GUIDELINES.md.

Logs are the developer plane (stdout JSON); the events table is the owner plane.
Secrets must never be logged — a scrubbing processor masks known-sensitive keys.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

# Keys whose values are always masked in log output, regardless of level.
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "secret",
        "api_secret",
        "api_key",
        "secret_encrypted",
        "master_key",
        "jwt_secret",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "totp_secret",
        "signature",
        "codex_api_key",
    }
)

_MASK = "***"


def _scrub_sensitive(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Mask values for known-sensitive keys before rendering."""
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = _MASK
    return event_dict


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Configure structlog + stdlib logging once at startup."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _scrub_sensitive,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level) if isinstance(level, str) else level
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
