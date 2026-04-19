"""Tests for host-side action execution helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ulanzi_linux.application.action_runner import ActionRunner
from ulanzi_linux.domain.button_config import ShellAction, UrlAction


def _disable_login_shell_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ActionRunner, "_login_shell_path", lambda self: None)


@pytest.mark.asyncio
async def test_url_action_prefers_xdg_open(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_login_shell_path(monkeypatch)
    runner = ActionRunner()
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "ulanzi_linux.application.action_runner.shutil.which",
        lambda name, path=None: "/usr/bin/xdg-open" if name == "xdg-open" else None,
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
    _disable_login_shell_path(monkeypatch)
    runner = ActionRunner()
    opened: list[str] = []

    monkeypatch.setattr(
        "ulanzi_linux.application.action_runner.shutil.which",
        lambda _name, path=None: None,
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

    await runner.run(UrlAction(type="url", url="example.com/fallback"))

    assert opened == ["https://example.com/fallback"]


def test_runner_builds_env_from_login_shell_and_user_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr(
        ActionRunner,
        "_login_shell_path",
        lambda self: "/opt/custom/bin:/snap/bin",
    )
    monkeypatch.setattr(
        ActionRunner,
        "_user_specific_path_entries",
        lambda self: [
            "/home/test/.local/bin",
            "/home/test/.local/share/flatpak/exports/bin",
        ],
    )

    runner = ActionRunner()

    assert runner._env["PATH"].split(":") == [
        "/opt/custom/bin",
        "/snap/bin",
        "/usr/bin",
        "/bin",
        "/home/test/.local/bin",
        "/home/test/.local/share/flatpak/exports/bin",
        "/usr/local/sbin",
        "/usr/local/bin",
        "/usr/sbin",
        "/sbin",
        "/var/lib/flatpak/exports/bin",
    ]


@pytest.mark.asyncio
async def test_shell_action_uses_augmented_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setattr(ActionRunner, "_login_shell_path", lambda self: "/opt/bin")
    monkeypatch.setattr(ActionRunner, "_user_specific_path_entries", lambda self: [])
    runner = ActionRunner()
    observed: dict[str, object] = {}

    class FakeProcess:
        async def wait(self) -> int:
            return 0

    async def fake_create_subprocess_shell(
        cmd: str,
        *,
        env: dict[str, str],
        stdout: object,
        stderr: object,
    ) -> FakeProcess:
        observed["cmd"] = cmd
        observed["env"] = env
        observed["stdout"] = stdout
        observed["stderr"] = stderr
        return FakeProcess()

    monkeypatch.setattr(
        "ulanzi_linux.application.action_runner.asyncio.create_subprocess_shell",
        fake_create_subprocess_shell,
    )

    await runner.run(ShellAction(type="shell", cmd="obsidian"))

    assert observed["cmd"] == "obsidian"
    assert observed["env"] == runner._env
    assert str(observed["env"]["PATH"]).startswith("/opt/bin:/usr/bin")
