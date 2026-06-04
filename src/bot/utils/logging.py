"""Structured logging via structlog."""

import logging
import sys
from typing import Any, cast

import structlog

_LEVELS = logging.getLevelNamesMapping()


def _resolve_level(level: str) -> int:
    """Return the numeric log level for *level*, raising ValueError for unknown names."""
    key = level.upper()
    if key not in _LEVELS:
        valid = ", ".join(sorted(_LEVELS))
        raise ValueError(f"Unknown log level {level!r}. Valid: {valid}")
    return _LEVELS[key]


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Configure structlog with the given level and output format."""
    numeric_level = _resolve_level(level)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if json_output:
        processors.append(structlog.processors.format_exc_info)
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to the given name."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
