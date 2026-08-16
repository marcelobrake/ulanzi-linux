"""Tests for the ``cycle_shortcut`` action — one button, alternating chords.

Covers the whole contract end to end: the domain guard, both YAML spellings,
where the daemon keeps its cursor (and when it resets), and the editor's
single comma-separated field.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import pytest
import yaml

# The daemon harness already exists; duplicating it here would just be a
# second thing to keep in sync with DeckDevice.
from tests.test_pagination import FakeDeck, RecordingRunner
from ulanzi_linux.application.action_runner import ActionRunner
from ulanzi_linux.application.config_loader import load_deck_config
from ulanzi_linux.application.daemon import DeckDaemon
from ulanzi_linux.application.deck_service import DeckService
from ulanzi_linux.domain.button_config import (
    ButtonConfig,
    CycleShortcutAction,
    DeckConfig,
    Page,
    ShortcutAction,
)
from ulanzi_linux.domain.device import DeckDevice

# ---------------------------------------------------------------------- #
# Domain                                                                  #
# ---------------------------------------------------------------------- #


def test_cycle_shortcut_wraps_after_the_last_key() -> None:
    action = CycleShortcutAction(type="cycle_shortcut", keys=("F23", "F24"))
    emitted = [action.shortcut_at(i).keys for i in range(5)]
    assert emitted == ["F23", "F24", "F23", "F24", "F23"]


def test_cycle_shortcut_resolves_to_a_plain_shortcut_action() -> None:
    action = CycleShortcutAction(type="cycle_shortcut", keys=("F23", "F24"))
    assert action.shortcut_at(1) == ShortcutAction(type="shortcut", keys="F24")


def test_cycle_shortcut_strips_blank_entries() -> None:
    action = CycleShortcutAction(
        type="cycle_shortcut",
        keys=(" F23 ", "", "  ", "F24"),
    )
    assert action.keys == ("F23", "F24")


def test_cycle_shortcut_rejects_a_single_key() -> None:
    with pytest.raises(ValueError, match="at least two shortcuts"):
        CycleShortcutAction(type="cycle_shortcut", keys=("F23",))


# ---------------------------------------------------------------------- #
# Config loader                                                           #
# ---------------------------------------------------------------------- #


def _write(tmp_path: Path, keys_yaml: str) -> Path:
    path = tmp_path / "deck.yaml"
    path.write_text(
        "default_page: main\n"
        "pages:\n"
        "  main:\n"
        "    buttons:\n"
        "      - index: 0\n"
        "        label: Toggle\n"
        f"        action: {{ type: cycle_shortcut, keys: {keys_yaml} }}\n",
        encoding="utf-8",
    )
    return path


def test_loader_accepts_a_yaml_list(tmp_path: Path) -> None:
    cfg = load_deck_config(_write(tmp_path, "[F23, F24]"))
    action = cfg.button_at("main", 0).action
    assert isinstance(action, CycleShortcutAction)
    assert action.keys == ("F23", "F24")


def test_loader_accepts_a_comma_separated_string(tmp_path: Path) -> None:
    cfg = load_deck_config(_write(tmp_path, '"F23, F24"'))
    action = cfg.button_at("main", 0).action
    assert isinstance(action, CycleShortcutAction)
    assert action.keys == ("F23", "F24")


def test_loader_rejects_a_single_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least two shortcuts"):
        load_deck_config(_write(tmp_path, "[F23]"))


def test_loader_rejects_keys_of_the_wrong_shape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="list or comma-separated string"):
        load_deck_config(_write(tmp_path, "17"))


# ---------------------------------------------------------------------- #
# Daemon                                                                  #
# ---------------------------------------------------------------------- #


def _cycle_button(index: int, *keys: str) -> ButtonConfig:
    return ButtonConfig(
        index=index,
        label=f"Cycle{index}",
        action=CycleShortcutAction(type="cycle_shortcut", keys=keys),
    )


async def _press(daemon: DeckDaemon, fake: FakeDeck, *indices: int) -> None:
    stop = asyncio.Event()

    async def drive() -> None:
        for index in indices:
            fake.inject_press(index)
            await asyncio.sleep(0.02)
        stop.set()

    await asyncio.gather(daemon.run(stop_event=stop), drive())


async def test_daemon_alternates_between_two_shortcuts() -> None:
    fake = FakeDeck()
    cfg = DeckConfig(
        pages={"main": Page(name="main", buttons=(_cycle_button(0, "F23", "F24"),))},
        default_page="main",
    )
    runner = RecordingRunner()

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg, runner=runner)
        await _press(daemon, fake, 0, 0, 0, 0)

    assert [a.keys for a in runner.actions] == ["F23", "F24", "F23", "F24"]
    # The runner only ever sees plain shortcuts — the cycle is daemon state.
    assert all(isinstance(a, ShortcutAction) for a in runner.actions)


async def test_daemon_keeps_a_separate_cursor_per_button() -> None:
    fake = FakeDeck()
    cfg = DeckConfig(
        pages={
            "main": Page(
                name="main",
                buttons=(
                    _cycle_button(0, "F23", "F24"),
                    _cycle_button(1, "F23", "F24"),
                ),
            )
        },
        default_page="main",
    )
    runner = RecordingRunner()

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg, runner=runner)
        await _press(daemon, fake, 0, 1, 0, 1)

    # Identical chord lists, but button 1's first press is still its first.
    assert [a.keys for a in runner.actions] == ["F23", "F23", "F24", "F24"]


async def test_daemon_shares_one_cursor_for_a_fixed_button_across_pages() -> None:
    fake = FakeDeck()
    cfg = DeckConfig(
        pages={
            "main": Page(name="main", buttons=()),
            "media": Page(name="media", buttons=()),
        },
        fixed_buttons=(_cycle_button(10, "F23", "F24"),),
        default_page="main",
    )
    runner = RecordingRunner()

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg, runner=runner)
        await _press(daemon, fake, 10)
        await daemon.switch_to("media")
        await _press(daemon, fake, 10)

    # One physical button, so switching pages must not rewind it to F23.
    assert [a.keys for a in runner.actions] == ["F23", "F24"]


async def test_reload_preserves_the_cursor_when_the_chords_are_unchanged(
    tmp_path: Path,
) -> None:
    fake = FakeDeck()
    path = _write(tmp_path, "[F23, F24]")
    cfg = load_deck_config(path)
    runner = RecordingRunner()

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg, runner=runner)
        await _press(daemon, fake, 0)
        # An edit elsewhere in the file: same button, same chords.
        path.write_text(
            path.read_text(encoding="utf-8").replace("Toggle", "Alternar"),
            encoding="utf-8",
        )
        await daemon.reload_config(path)
        await _press(daemon, fake, 0)

    assert [a.keys for a in runner.actions] == ["F23", "F24"]


async def test_reload_restarts_the_cycle_when_the_chords_change(
    tmp_path: Path,
) -> None:
    fake = FakeDeck()
    path = _write(tmp_path, "[F23, F24]")
    cfg = load_deck_config(path)
    runner = RecordingRunner()

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg, runner=runner)
        await _press(daemon, fake, 0)
        _write(tmp_path, "[F21, F22]")
        await daemon.reload_config(path)
        await _press(daemon, fake, 0)

    assert [a.keys for a in runner.actions] == ["F23", "F21"]
    # The stale cursor is dropped rather than accumulating across reloads.
    assert len(daemon._cycle_cursors) == 1


# ---------------------------------------------------------------------- #
# Action runner fallback                                                  #
# ---------------------------------------------------------------------- #


async def test_runner_alternates_when_called_without_the_daemon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ActionRunner, "_login_shell_path", lambda self: None)
    runner = ActionRunner()
    dispatched: list[str] = []

    async def fake_run_shortcut(self: ActionRunner, action: ShortcutAction) -> None:
        dispatched.append(action.keys)

    async def no_session_agent(self: ActionRunner, action: object) -> bool:
        return False

    monkeypatch.setattr(ActionRunner, "_run_shortcut", fake_run_shortcut)
    monkeypatch.setattr(ActionRunner, "_delegate_to_session_agent", no_session_agent)

    action = CycleShortcutAction(type="cycle_shortcut", keys=("F23", "F24"))
    for _ in range(3):
        await runner.run(action)

    assert dispatched == ["F23", "F24", "F23"]


# ---------------------------------------------------------------------- #
# Web editor                                                              #
# ---------------------------------------------------------------------- #

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from ulanzi_linux.interface.web.app import create_app  # noqa: E402


def _editor_client(tmp_path: Path) -> tuple[TestClient, Path]:
    path = _write(tmp_path, "[F23, F24]")
    return TestClient(create_app(path)), path


def test_editor_joins_cycle_keys_into_one_field(tmp_path: Path) -> None:
    client, _ = _editor_client(tmp_path)
    action = client.get("/api/editor").json()["pages"][0]["buttons"][0]["action"]
    assert action["type"] == "cycle_shortcut"
    assert action["keys"] == "F23, F24"


def test_put_editor_writes_cycle_keys_as_a_yaml_list(tmp_path: Path) -> None:
    client, path = _editor_client(tmp_path)
    payload = client.get("/api/editor").json()
    payload["pages"][0]["buttons"][0]["action"]["keys"] = "F23,F24 , F21"

    response = client.put("/api/editor", json=payload)
    assert response.status_code == 200

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    saved = doc["pages"]["main"]["buttons"][0]["action"]
    assert saved == {"type": "cycle_shortcut", "keys": ["F23", "F24", "F21"]}


def test_put_editor_rejects_a_single_cycle_key(tmp_path: Path) -> None:
    client, path = _editor_client(tmp_path)
    before = path.read_text(encoding="utf-8")
    payload = client.get("/api/editor").json()
    payload["pages"][0]["buttons"][0]["action"]["keys"] = "F23"

    response = client.put("/api/editor", json=payload)
    assert response.status_code == 422
    assert "at least two shortcuts" in response.json()["error"]
    # Rejected saves must never touch the file on disk.
    assert path.read_text(encoding="utf-8") == before
