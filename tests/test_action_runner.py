"""Tests for host-side action execution helpers."""

from __future__ import annotations

import asyncio

import pytest

from ulanzi_linux.application.action_runner import ActionRunner
from ulanzi_linux.application.session_agent import SessionAgentDispatchResult
from ulanzi_linux.domain.button_config import ShellAction, UrlAction


def _disable_login_shell_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ActionRunner, "_login_shell_path", lambda self: None)


def _disable_desktop_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ActionRunner, "_desktop_launch_target", lambda self, _cmd: None)


def _disable_browser_focus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ActionRunner, "_default_browser_target", lambda self: None)


def _disable_session_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unavailable(
        self: ActionRunner,
        _action: object,
    ) -> bool:
        return False

    monkeypatch.setattr(ActionRunner, "_delegate_to_session_agent", _unavailable)


@pytest.mark.asyncio
async def test_url_action_prefers_gio_open(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_login_shell_path(monkeypatch)
    _disable_browser_focus(monkeypatch)
    _disable_session_agent(monkeypatch)
    runner = ActionRunner()
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "ulanzi_linux.application.action_runner.shutil.which",
        lambda name, path=None: "/usr/bin/" + name if name in {"gio", "xdg-open"} else None,
    )

    async def fake_try_exec(argv: list[str]) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr(runner, "_try_exec", fake_try_exec)

    await runner.run(UrlAction(type="url", url="https://example.com"))

    assert calls == [["gio", "open", "https://example.com"]]


@pytest.mark.asyncio
async def test_url_action_prefers_default_browser_exec_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_login_shell_path(monkeypatch)
    _disable_session_agent(monkeypatch)
    runner = ActionRunner()
    calls: list[list[str]] = []
    focus_calls: list[object] = []
    fake_target = type(
        "FakeBrowserTarget",
        (),
        {
            "desktop_id": "google-chrome.desktop",
            "window_tokens": ("google-chrome",),
        },
    )()

    monkeypatch.setattr(
        runner,
        "_default_browser_url_candidate",
        lambda url, browser_target=None: (fake_target, ["/usr/bin/google-chrome-stable", url]),
    )
    monkeypatch.setattr(runner, "_default_browser_target", lambda: fake_target)
    monkeypatch.setattr(runner, "_focus_existing_desktop_target", lambda _target: asyncio.sleep(0, result=None))

    async def fake_try_exec(argv: list[str]) -> int:
        calls.append(argv)
        return 0

    async def fake_focus_desktop_target(target: object) -> str:
        focus_calls.append(target)
        return "0x028001fe"

    monkeypatch.setattr(runner, "_try_exec", fake_try_exec)
    monkeypatch.setattr(runner, "_focus_desktop_target", fake_focus_desktop_target)

    await runner.run(UrlAction(type="url", url="https://example.com"))

    assert calls == [["/usr/bin/google-chrome-stable", "https://example.com"]]
    assert focus_calls == [fake_target]


@pytest.mark.asyncio
async def test_url_action_falls_back_to_webbrowser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_login_shell_path(monkeypatch)
    _disable_browser_focus(monkeypatch)
    _disable_session_agent(monkeypatch)
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
    monkeypatch.setattr(
        loop,
        "run_in_executor",
        lambda _executor, fn, url: asyncio.sleep(0, result=fn(url)),
    )
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
    _disable_desktop_launch(monkeypatch)
    _disable_session_agent(monkeypatch)
    runner = ActionRunner()
    observed: dict[str, object] = {}

    class FakeProcess:
        pid = 1234

        async def wait(self) -> int:
            return 0

    async def fake_create_subprocess_shell(
        cmd: str,
        *,
        env: dict[str, str],
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        observed["cmd"] = cmd
        observed["env"] = env
        observed["cwd"] = cwd
        observed["stdin"] = stdin
        observed["stdout"] = stdout
        observed["stderr"] = stderr
        observed["start_new_session"] = start_new_session
        return FakeProcess()

    monkeypatch.setattr(
        "ulanzi_linux.application.action_runner.asyncio.create_subprocess_shell",
        fake_create_subprocess_shell,
    )

    await runner.run(ShellAction(type="shell", cmd="obsidian"))

    assert observed["cmd"] == "obsidian"
    assert observed["env"] == runner._env
    assert str(observed["env"]["PATH"]).startswith("/opt/bin:/usr/bin")


@pytest.mark.asyncio
async def test_shell_action_prefers_desktop_launcher_for_simple_apps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_login_shell_path(monkeypatch)
    _disable_session_agent(monkeypatch)
    runner = ActionRunner()
    calls: list[list[str]] = []
    focus_calls: list[object] = []
    tasks: list[asyncio.Task[object]] = []
    fake_target = type(
        "FakeTarget",
        (),
        {
            "desktop_id": "claude-desktop.desktop",
            "window_tokens": ("claude",),
        },
    )()
    real_create_task = asyncio.create_task

    monkeypatch.setattr(runner, "_desktop_launch_target", lambda cmd: fake_target)
    monkeypatch.setattr(
        runner,
        "_desktop_launch_candidates",
        lambda _target: [["gtk-launch", "claude-desktop.desktop"]],
    )
    monkeypatch.setattr(runner, "_focus_existing_desktop_target", lambda _target: asyncio.sleep(0, result=None))

    def fake_create_task(coro: object, *, name: str | None = None) -> asyncio.Task[object]:
        task = real_create_task(coro, name=name)
        tasks.append(task)
        return task

    async def fake_focus_desktop_target_with_retries(
        target: object,
        *,
        retries: int,
        delay_s: float = 0.25,
    ) -> str:
        focus_calls.append(target)
        return "0x01200004"

    async def fake_try_exec(argv: list[str]) -> int:
        calls.append(argv)
        return 0

    async def unexpected_create_subprocess_shell(
        cmd: str,
        *,
        env: dict[str, str],
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> object:
        raise AssertionError(f"desktop launch should avoid shell spawn: {cmd}")

    monkeypatch.setattr(runner, "_try_exec", fake_try_exec)
    monkeypatch.setattr(
        runner,
        "_focus_desktop_target_with_retries",
        fake_focus_desktop_target_with_retries,
    )
    monkeypatch.setattr(
        "ulanzi_linux.application.action_runner.asyncio.create_task",
        fake_create_task,
    )
    monkeypatch.setattr(
        "ulanzi_linux.application.action_runner.asyncio.create_subprocess_shell",
        unexpected_create_subprocess_shell,
    )

    await runner.run(ShellAction(type="shell", cmd="claude-desktop"))
    await asyncio.gather(*tasks)

    assert calls == [["gtk-launch", "claude-desktop.desktop"]]
    assert focus_calls == [fake_target]


@pytest.mark.asyncio
async def test_shell_action_reuses_existing_window_before_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_login_shell_path(monkeypatch)
    _disable_session_agent(monkeypatch)
    runner = ActionRunner()
    fake_target = type(
        "FakeTarget",
        (),
        {
            "aliases": ("chatgpt-desktop",),
            "desktop_id": "chatgpt-desktop_chatgpt-desktop.desktop",
            "window_tokens": ("chatgpt desktop",),
        },
    )()

    monkeypatch.setattr(runner, "_desktop_targets_for_session", lambda: (fake_target,))
    monkeypatch.setattr(
        runner,
        "_focus_existing_desktop_target",
        lambda _target: asyncio.sleep(0, result="0x06800004"),
    )

    async def unexpected_try_exec(argv: list[str]) -> int:
        raise AssertionError(f"existing window should avoid desktop launch: {argv}")

    monkeypatch.setattr(runner, "_try_exec", unexpected_try_exec)

    await runner.run(
        ShellAction(type="shell", cmd="chatgpt-desktop --disable-gpu --no-sandbox")
    )


@pytest.mark.asyncio
async def test_shell_action_tries_desktop_launcher_after_shell_failure_with_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    _disable_login_shell_path(monkeypatch)
    _disable_session_agent(monkeypatch)
    runner = ActionRunner()
    fallback_calls: list[tuple[str, object]] = []
    observed: dict[str, object] = {}
    fake_target = type(
        "FakeTarget",
        (),
        {
            "aliases": ("chatgpt-desktop",),
            "desktop_id": "chatgpt-desktop_chatgpt-desktop.desktop",
            "window_tokens": ("chatgpt desktop",),
        },
    )()

    monkeypatch.setattr(runner, "_desktop_targets_for_session", lambda: (fake_target,))
    monkeypatch.setattr(runner, "_focus_existing_desktop_target", lambda _target: asyncio.sleep(0, result=None))
    monkeypatch.setattr(
        runner,
        "_focus_desktop_target_with_retries",
        lambda _target, *, retries, delay_s=0.25: asyncio.sleep(0, result=None),
    )

    class FakeProcess:
        pid = 777

        async def wait(self) -> int:
            return 1

    async def fake_launch_desktop_target(cmd: str, target: object) -> bool:
        fallback_calls.append((cmd, target))
        return True

    async def fake_create_subprocess_shell(
        cmd: str,
        *,
        env: dict[str, str],
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        observed["cmd"] = cmd
        observed["cwd"] = cwd
        return FakeProcess()

    monkeypatch.setattr(runner, "_launch_desktop_target", fake_launch_desktop_target)
    monkeypatch.setattr(
        "ulanzi_linux.application.action_runner.asyncio.create_subprocess_shell",
        fake_create_subprocess_shell,
    )

    await runner.run(
        ShellAction(type="shell", cmd="chatgpt-desktop --disable-gpu --no-sandbox")
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert observed["cmd"] == "chatgpt-desktop --disable-gpu --no-sandbox"
    assert fallback_calls == [
        ("chatgpt-desktop --disable-gpu --no-sandbox", fake_target)
    ]


@pytest.mark.asyncio
async def test_url_action_focuses_default_browser_after_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_login_shell_path(monkeypatch)
    _disable_session_agent(monkeypatch)
    runner = ActionRunner()
    calls: list[list[str]] = []
    focus_calls: list[object] = []
    fake_target = type(
        "FakeBrowserTarget",
        (),
        {
            "desktop_id": "google-chrome.desktop",
            "window_tokens": ("google-chrome",),
        },
    )()

    monkeypatch.setattr(
        "ulanzi_linux.application.action_runner.shutil.which",
        lambda name, path=None: "/usr/bin/" + name if name == "gio" else None,
    )

    async def fake_try_exec(argv: list[str]) -> int:
        calls.append(argv)
        return 0

    async def fake_focus_desktop_target(target: object) -> str:
        focus_calls.append(target)
        return "0x01400007"

    monkeypatch.setattr(runner, "_try_exec", fake_try_exec)
    monkeypatch.setattr(runner, "_default_browser_target", lambda: fake_target)
    monkeypatch.setattr(runner, "_default_browser_url_candidate", lambda url, browser_target=None: None)
    monkeypatch.setattr(runner, "_focus_existing_desktop_target", lambda _target: asyncio.sleep(0, result=None))
    monkeypatch.setattr(runner, "_focus_desktop_target", fake_focus_desktop_target)

    await runner.run(UrlAction(type="url", url="https://example.com"))

    assert calls == [["gio", "open", "https://example.com"]]
    assert focus_calls == [fake_target]


@pytest.mark.asyncio
async def test_shell_action_logs_nonzero_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_login_shell_path(monkeypatch)
    _disable_desktop_launch(monkeypatch)
    _disable_session_agent(monkeypatch)
    runner = ActionRunner()
    warnings: list[dict[str, object]] = []

    class FakeProcess:
        pid = 4321

        async def wait(self) -> int:
            return 127

    async def fake_create_subprocess_shell(
        cmd: str,
        *,
        env: dict[str, str],
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        return FakeProcess()

    monkeypatch.setattr(
        "ulanzi_linux.application.action_runner.asyncio.create_subprocess_shell",
        fake_create_subprocess_shell,
    )
    monkeypatch.setattr(
        "ulanzi_linux.application.action_runner.logger.warning",
        lambda event, **kwargs: warnings.append({"event": event, **kwargs}),
    )

    await runner.run(ShellAction(type="shell", cmd="chatgpt"))
    await asyncio.sleep(0)

    assert warnings == [
        {
            "event": "action_shell_failed",
            "cmd": "chatgpt",
            "pid": 4321,
            "exit_code": 127,
        }
    ]


@pytest.mark.asyncio
async def test_runner_delegates_shell_action_to_session_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_login_shell_path(monkeypatch)
    runner = ActionRunner()
    calls: list[object] = []

    async def fake_dispatch(action: object) -> SessionAgentDispatchResult:
        calls.append(action)
        return SessionAgentDispatchResult(status="accepted", detail="shell_nohup")

    async def unexpected_run_shell(_action: object) -> None:
        raise AssertionError("local shell path should not run when session agent accepts")

    monkeypatch.setattr(runner._session_agent, "dispatch", fake_dispatch)
    monkeypatch.setattr(runner, "_run_shell", unexpected_run_shell)

    action = ShellAction(type="shell", cmd="postman")
    await runner.run(action)

    assert calls == [action]
