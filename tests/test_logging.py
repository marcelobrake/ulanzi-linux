"""Tests for the structured logging bootstrap and syslog mirroring."""

from __future__ import annotations

import structlog

from ulanzi_linux.observability import logging as logging_module


class FakeSyslogModule:
    """Small syslog stub to verify emitted priorities and payloads."""

    LOG_PID = 1
    LOG_USER = 8
    LOG_DEBUG = 7
    LOG_INFO = 6
    LOG_WARNING = 4
    LOG_ERR = 3
    LOG_CRIT = 2

    def __init__(self) -> None:
        self.openlog_calls: list[tuple[str, int, int]] = []
        self.syslog_calls: list[tuple[int, str]] = []
        self.closed = False

    def openlog(self, ident: str, logoption: int, facility: int) -> None:
        self.openlog_calls.append((ident, logoption, facility))

    def syslog(self, priority: int, message: str) -> None:
        self.syslog_calls.append((priority, message))

    def closelog(self) -> None:
        self.closed = True


def test_configure_logging_mirrors_structlog_events_to_syslog(
    monkeypatch,
) -> None:
    fake_syslog = FakeSyslogModule()
    monkeypatch.setattr(logging_module, "_syslog_module", fake_syslog)
    monkeypatch.setattr(
        logging_module,
        "SYSLOG_LEVELS",
        {
            "critical": fake_syslog.LOG_CRIT,
            "error": fake_syslog.LOG_ERR,
            "warning": fake_syslog.LOG_WARNING,
            "info": fake_syslog.LOG_INFO,
            "debug": fake_syslog.LOG_DEBUG,
        },
    )

    logging_module.configure_logging(json_output=True, syslog_output=True)
    structlog.get_logger("tests").warning(
        "action_shell_failed",
        cmd="chatgpt",
        exit_code=127,
    )

    assert fake_syslog.openlog_calls == [
        ("ulanzi-linux", fake_syslog.LOG_PID, fake_syslog.LOG_USER)
    ]
    assert fake_syslog.syslog_calls
    priority, message = fake_syslog.syslog_calls[-1]
    assert priority == fake_syslog.LOG_WARNING
    assert '"event": "action_shell_failed"' in message
    assert '"cmd": "chatgpt"' in message
    assert '"exit_code": 127' in message
