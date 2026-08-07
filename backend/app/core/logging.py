"""Structured logging setup.

Two things matter here:

1. Development gets human-readable console output; production gets JSON so
   logs can be shipped and queried.
2. Secrets never reach a log sink.  ``_redact_secrets`` scrubs known-sensitive
   keys from every event dict before it is rendered.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.typing import EventDict, WrappedLogger

# Substrings that mark a value as sensitive.  Matched case-insensitively
# against the *key*, so `api_key`, `X-Admin-Token` and `password` all match.
_SENSITIVE_KEY_PARTS: tuple[str, ...] = (
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "x-rapidapi-key",
    "credential",
    "dsn",
    "database_url",
)

_REDACTED = "***redacted***"


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _redact_secrets(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    """Replace the value of any sensitive-looking key with a placeholder.

    Recurses one level into nested dicts, which is where request headers and
    provider payloads normally live.
    """

    def scrub(value: Any, depth: int = 0) -> Any:
        if depth > 4:
            return value
        if isinstance(value, dict):
            return {
                k: (_REDACTED if _is_sensitive(str(k)) else scrub(v, depth + 1))
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple)):
            return type(value)(scrub(v, depth + 1) for v in value)
        return value

    return {
        key: (_REDACTED if _is_sensitive(str(key)) else scrub(val))
        for key, val in event_dict.items()
    }


def configure_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    """Configure structlog and route stdlib logging through it."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _redact_secrets,
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        # Must be the stdlib factory: `add_logger_name` reads `logger.name`,
        # which only real stdlib loggers expose. Pairing it with a PrintLogger
        # raises AttributeError from inside the logging call itself.
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=numeric_level,
        force=True,
    )
    # uvicorn installs its own handlers; let them propagate to the root logger
    # instead of double-printing through their own formatters.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(noisy).handlers.clear()
        logging.getLogger(noisy).propagate = True

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
