"""Structured logging bootstrap.

We use ``structlog`` configured to emit JSON in production and human-friendly
coloured output in development. The configuration is idempotent — calling
``configure_logging`` multiple times is safe.

The processor chain is explicit on purpose: it makes it trivial to later bolt
on OpenTelemetry trace/span enrichment without restructuring callers.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog


def configure_logging(
    *,
    level: str | int = "INFO",
    json_output: bool | None = None,
    include_caller: bool = False,
) -> None:
    """Configure ``structlog`` and the stdlib ``logging`` module together.

    Args:
        level: Minimum log level (name or numeric).
        json_output: Force JSON rendering. If ``None``, auto-detects by
            looking at ``stderr.isatty()`` — a TTY means pretty output.
        include_caller: Attach file/line/function info. Slightly expensive,
            disabled by default.

    Environment variable override:
        ``ULANZI_LOG_LEVEL`` takes precedence over the ``level`` argument
        when set, so users can flip verbosity without code changes.
    """
    env_level = os.environ.get("ULANZI_LOG_LEVEL")
    effective_level = env_level if env_level else level
    numeric_level = (
        logging.getLevelName(effective_level.upper())
        if isinstance(effective_level, str)
        else int(effective_level)
    )

    if json_output is None:
        json_output = not sys.stderr.isatty()

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if include_caller:
        shared_processors.append(
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                ]
            )
        )

    renderer: Any
    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Keep the stdlib logger in sync so third-party libraries using
    # ``logging.*`` respect the same level.
    logging.basicConfig(
        level=numeric_level,
        format="%(message)s",
        stream=sys.stderr,
        force=True,
    )


__all__ = ["configure_logging"]
