"""Tests for host-side action execution helpers."""

from __future__ import annotations

import asyncio

import pytest

from ulanzi_linux.application.action_runner import ActionRunner
from ulanzi_linux.domain.button_config import UrlAction


@pytest.mark.asyncio
async def test_url_action_prefers_xdg_open(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = ActionRunner()
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "ulanzi_linux.application.action_runner.shutil.which",
        lambda name: "/usr/bin/xdg-open" if name == "xdg-open" else None,
    )

    async def fake_try_exec(argv: list[str]) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr(runner, "_try_exec", fake_try_exec)

    await runner.run(UrlAction(type="url", url="https://example.com"))

    assert calls == [["xdg-open", "https://example.com"]]


@pytest.mark.asyncio
async def test_url_action_falls_back_to_webbrowser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = ActionRunner()
    opened: list[str] = []

    monkeypatch.setattr(
        "ulanzi_linux.application.action_runner.shutil.which",
        lambda _name: None,
    )

    def fake_open(url: str) -> bool:
        opened.append(url)
        return True

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "run_in_executor", lambda _executor, fn, url: asyncio.sleep(0, result=fn(url)))
    monkeypatch.setattr(
        "ulanzi_linux.application.action_runner.webbrowser.open",
        fake_open,
    )

    await runner.run(UrlAction(type="url", url="https://example.com/fallback"))

    assert opened == ["https://example.com/fallback"]