"""Structured JSON logging (structlog) per docs/guidelines/LOGGING_GUIDELINES.md.

Logs are the developer plane (stdout JSON); the events table is the owner plane.
Secrets must never be logged — a scrubbing processor masks known-sensitive keys.
"""

from __future__ import annotations

import logging
import re
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
        "otp",
        "otp_code",
        "otp_token",
        "verification_code",
        "code",
        "code_hash",
        "phone",
        "phone_encrypted",
        "signature",
        "codex_api_key",
    }
)

_MASK = "***"
_OTP_IN_TEXT = re.compile(r"(?i)\b(code|otp)\s*[:=]?\s*[0-9]{6}\b")
_PHONE_IN_TEXT = re.compile(r"(?<![0-9])(?:\+?94)[0-9]{9}(?![0-9])")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|authorization|password|secret|signature|token)"
    r"(\s*[=:]\s*|%3[dD])([^\s,;&\"'}]+)"
)


def _scrub_value(value: Any) -> Any:
    if isinstance(value, MutableMapping):
        for key in list(value.keys()):
            value[key] = _MASK if key.lower() in _SENSITIVE_KEYS else _scrub_value(value[key])
        return value
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_value(item) for item in value)
    if isinstance(value, str):
        value = _OTP_IN_TEXT.sub(lambda match: f"{match.group(1)} {_MASK}", value)
        value = _PHONE_IN_TEXT.sub(_MASK, value)
        return _SECRET_ASSIGNMENT.sub(
            lambda match: f"{match.group(1)}{match.group(2)}{_MASK}", value
        )
    return value


def _scrub_sensitive(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Mask values for known-sensitive keys before rendering."""
    _scrub_value(event_dict)
    return event_dict


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Configure structlog + stdlib logging once at startup."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    # httpx's INFO message includes the complete request URL. Signed Binance
    # requests carry a short-lived authentication signature in the query
    # string, so third-party transport loggers must never emit request URLs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

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
