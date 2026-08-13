"""Tests for shortcut backend selection and keysym -> evdev translation."""

from __future__ import annotations

import pytest

from ulanzi_linux.application.action_runner import ActionRunner
from ulanzi_linux.domain.button_config import ShortcutAction
from ulanzi_linux.infrastructure.keysym_evdev import (
    keysym_to_evdev,
    translate_shortcut,
)


def _runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    wayland: bool,
    available: set[str],
    exit_codes: dict[str, int] | None = None,
) -> tuple[ActionRunner, list[list[str]]]:
    """Build a runner with a stubbed session type, PATH lookup, and exec."""
    monkeypatch.setattr(ActionRunner, "_login_shell_path", lambda self: None)
    runner = ActionRunner()
    session_env = (
        {"WAYLAND_DISPLAY": "wayland-0", "XDG_SESSION_TYPE": "wayland"}
        if wayland
        else {"DISPLAY": ":0"}
    )
    runner._env = {"PATH": "/usr/bin", **session_env}

    calls: list[list[str]] = []
    codes = exit_codes or {}

    def fake_which(self: ActionRunner, executable: str) -> str | None:
        return f"/usr/bin/{executable}" if executable in available else None

    async def fake_try_exec(self: ActionRunner, argv: list[str]) -> int:
        calls.append(argv)
        return codes.get(argv[0], 0)

    monkeypatch.setattr(ActionRunner, "_which", fake_which)
    monkeypatch.setattr(ActionRunner, "_try_exec", fake_try_exec)
    return runner, calls


# --- translation -----------------------------------------------------------


def test_single_keysym_translates_to_press_and_release() -> None:
    # KEY_PLAYPAUSE is 164 in the kernel ABI.
    assert translate_shortcut("XF86AudioPlay") == ["164:1", "164:0"]


def test_chord_releases_in_reverse_order() -> None:
    # ctrl=29, alt=56, t=20 — modifiers must release after the main key.
    assert translate_shortcut("ctrl+alt+t") == [
        "29:1",
        "56:1",
        "20:1",
        "20:0",
        "56:0",
        "29:0",
    ]


def test_modifier_aliases_are_accepted() -> None:
    assert translate_shortcut("super+l") == translate_shortcut("Super_L+l")


def test_unknown_keysym_returns_none() -> None:
    assert translate_shortcut("XF86NotARealKey") is None
    assert keysym_to_evdev("definitely_not_a_key") is None


# --- backend selection -----------------------------------------------------


@pytest.mark.asyncio
async def test_wayland_prefers_ydotool(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, calls = _runner(
        monkeypatch, wayland=True, available={"xdotool", "ydotool"}
    )
    await runner._run_shortcut(ShortcutAction(type="shortcut", keys="XF86AudioPlay"))
    assert calls == [["ydotool", "key", "164:1", "164:0"]]


@pytest.mark.asyncio
async def test_x11_prefers_xdotool(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, calls = _runner(
        monkeypatch, wayland=False, available={"xdotool", "ydotool"}
    )
    await runner._run_shortcut(ShortcutAction(type="shortcut", keys="XF86AudioPlay"))
    assert calls == [["xdotool", "key", "XF86AudioPlay"]]


@pytest.mark.asyncio
async def test_untranslatable_keys_fall_back_to_xdotool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A keysym outside the table must not be dropped — xdotool still knows it."""
    runner, calls = _runner(
        monkeypatch, wayland=True, available={"xdotool", "ydotool"}
    )
    await runner._run_shortcut(ShortcutAction(type="shortcut", keys="XF86Xfer"))
    assert calls == [["xdotool", "key", "XF86Xfer"]]


@pytest.mark.asyncio
async def test_ydotool_failure_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """ydotoold not running -> non-zero exit -> next backend gets a turn."""
    runner, calls = _runner(
        monkeypatch,
        wayland=True,
        available={"xdotool", "ydotool"},
        exit_codes={"ydotool": 1},
    )
    await runner._run_shortcut(ShortcutAction(type="shortcut", keys="XF86AudioPlay"))
    assert [argv[0] for argv in calls] == ["ydotool", "xdotool"]


@pytest.mark.asyncio
async def test_no_backend_available_is_not_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, calls = _runner(monkeypatch, wayland=True, available=set())
    await runner._run_shortcut(ShortcutAction(type="shortcut", keys="XF86AudioPlay"))
    assert calls == []


@pytest.mark.asyncio
async def test_first_success_stops_the_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, calls = _runner(
        monkeypatch, wayland=True, available={"xdotool", "ydotool", "wtype"}
    )
    await runner._run_shortcut(ShortcutAction(type="shortcut", keys="ctrl+alt+t"))
    assert len(calls) == 1
    assert calls[0][0] == "ydotool"
