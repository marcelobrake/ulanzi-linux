"""Structured logging bootstrap.

We use ``structlog`` configured to emit JSON in production and human-friendly
coloured output in development. The configuration is idempotent — calling
``configure_logging`` multiple times is safe.

The processor chain is explicit on purpose: it makes it trivial to later bolt
on OpenTelemetry trace/span enrichment without restructuring callers.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
from typing import Any

import structlog

try:
    import syslog as _syslog_module
except ImportError:  # pragma: no cover - non-POSIX platforms only
    _syslog_module = None

SYSLOG_IDENT = "ulanzi-linux"
SYSLOG_ENV_VAR = "ULANZI_SYSLOG"
SYSLOG_RENDERER = structlog.processors.JSONRenderer()
SYSLOG_LEVELS: dict[str, int] = (
    {
        "critical": _syslog_module.LOG_CRIT,
        "error": _syslog_module.LOG_ERR,
        "warning": _syslog_module.LOG_WARNING,
        "info": _syslog_module.LOG_INFO,
        "debug": _syslog_module.LOG_DEBUG,
    }
    if _syslog_module is not None
    else {}
)
_SYSLOG_ENABLED = False


def _parse_bool_env(raw: str | None) -> bool | None:
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def _configure_syslog(enabled: bool) -> None:
    global _SYSLOG_ENABLED

    if _syslog_module is None:
        _SYSLOG_ENABLED = False
        return

    if not enabled:
        with contextlib.suppress(OSError):
            _syslog_module.closelog()
        _SYSLOG_ENABLED = False
        return

    try:
        _syslog_module.openlog(
            ident=SYSLOG_IDENT,
            logoption=_syslog_module.LOG_PID,
            facility=_syslog_module.LOG_USER,
        )
    except OSError:
        _SYSLOG_ENABLED = False
        return

    _SYSLOG_ENABLED = True


def _syslog_priority_for(level: str) -> int:
    if _syslog_module is None:
        return 0
    return SYSLOG_LEVELS.get(level.lower(), _syslog_module.LOG_INFO)


def _render_syslog_payload(event_dict: dict[str, Any]) -> str:
    try:
        rendered = SYSLOG_RENDERER(None, "", dict(event_dict))
        return rendered if isinstance(rendered, str) else str(rendered)
    except Exception:
        return " ".join(
            f"{key}={value!r}" for key, value in sorted(event_dict.items())
        )


def _forward_to_syslog(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    if not _SYSLOG_ENABLED or _syslog_module is None:
        return event_dict

    with contextlib.suppress(OSError):
        _syslog_module.syslog(
            _syslog_priority_for(str(event_dict.get("level", "info"))),
            _render_syslog_payload(event_dict),
        )
    return event_dict


def configure_logging(
    *,
    level: str | int = "INFO",
    json_output: bool | None = None,
    syslog_output: bool | None = None,
    include_caller: bool = False,
) -> None:
    """Configure ``structlog`` and the stdlib ``logging`` module together.

    Args:
        level: Minimum log level (name or numeric).
        json_output: Force JSON rendering. If ``None``, auto-detects by
            looking at ``stderr.isatty()`` — a TTY means pretty output.
        syslog_output: Mirror structured logs to the host syslog facility.
            If ``None``, auto-enables on POSIX unless ``ULANZI_SYSLOG=0``.
        include_caller: Attach file/line/function info. Slightly expensive,
            disabled by default.

    Environment variable override:
        ``ULANZI_LOG_LEVEL`` takes precedence over the ``level`` argument
        when set, so users can flip verbosity without code changes.
        ``ULANZI_SYSLOG`` overrides the ``syslog_output`` argument when set.
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

    env_syslog = _parse_bool_env(os.environ.get(SYSLOG_ENV_VAR))
    auto_syslog = os.name == "posix" and "JOURNAL_STREAM" not in os.environ
    effective_syslog = (
        env_syslog
        if env_syslog is not None
        else (auto_syslog if syslog_output is None else syslog_output)
    )
    _configure_syslog(effective_syslog)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if _SYSLOG_ENABLED:
        shared_processors.append(_forward_to_syslog)
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
