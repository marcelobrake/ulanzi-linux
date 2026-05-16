"""Tests for the multi-page DeckConfig + daemon page switching."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest

from ulanzi_linux.application.config_loader import load_deck_config
from ulanzi_linux.application.daemon import DeckDaemon
from ulanzi_linux.application.deck_service import DeckService
from ulanzi_linux.domain.button_config import (
    ButtonConfig,
    DeckConfig,
    Page,
    PredefinedCommandAction,
    ShellAction,
    SwitchPageAction,
    TextStyle,
    UrlAction,
)
from ulanzi_linux.domain.commands import SmallWindowMode
from ulanzi_linux.domain.device import DeckDevice, DeckSpec
from ulanzi_linux.domain.events import ButtonEvent, DeviceInfoEvent

# ---------------------------------------------------------------------- #
# Domain tests                                                           #
# ---------------------------------------------------------------------- #


def _btn(index: int, label: str = "", action=None) -> ButtonConfig:
    return ButtonConfig(index=index, label=label, action=action)


def test_single_page_helper_wraps_legacy_config() -> None:
    cfg = DeckConfig.single_page((_btn(0, "A"), _btn(1, "B")))
    assert cfg.default_page == "default"
    assert len(cfg.pages) == 1
    assert cfg.buttons_for("default") == (_btn(0, "A"), _btn(1, "B"))


def test_buttons_for_combines_page_and_fixed() -> None:
    cfg = DeckConfig(
        pages={
            "main": Page(name="main", buttons=(_btn(0, "A"),)),
            "media": Page(name="media", buttons=(_btn(0, "P"),)),
        },
        fixed_buttons=(_btn(10, "SwMain"),),
        default_page="main",
    )
    assert cfg.buttons_for("main") == (_btn(0, "A"), _btn(10, "SwMain"))
    assert cfg.buttons_for("media") == (_btn(0, "P"), _btn(10, "SwMain"))


def test_rejects_fixed_button_colliding_with_page_index() -> None:
    with pytest.raises(ValueError, match="reuses fixed_button indices"):
        DeckConfig(
            pages={"main": Page(name="main", buttons=(_btn(10, "X"),))},
            fixed_buttons=(_btn(10, "Sw"),),
            default_page="main",
        )


def test_rejects_missing_default_page() -> None:
    with pytest.raises(ValueError, match="default_page"):
        DeckConfig(
            pages={"main": Page(name="main", buttons=())},
            default_page="nope",
        )


# ---------------------------------------------------------------------- #
# Config loader tests                                                    #
# ---------------------------------------------------------------------- #


def test_loader_parses_multi_page_yaml(tmp_path: Path) -> None:
    yaml_text = """
default_page: main
pages:
  main:
    buttons:
      - index: 0
        label: A
  media:
    buttons:
      - index: 0
        label: P
fixed_buttons:
  - index: 10
    label: SwMain
    action: { type: switch_page, page: main }
  - index: 11
    label: SwMedia
    action: { type: switch_page, page: media }
"""
    path = tmp_path / "deck.yaml"
    path.write_text(yaml_text)
    cfg = load_deck_config(path)

    assert set(cfg.pages.keys()) == {"main", "media"}
    assert cfg.default_page == "main"
    assert len(cfg.fixed_buttons) == 2
    assert isinstance(cfg.fixed_buttons[0].action, SwitchPageAction)
    assert cfg.fixed_buttons[0].action.page == "main"


def test_loader_accepts_info_window_action_slot(tmp_path: Path) -> None:
    yaml_text = """
default_page: main
pages:
  main:
    buttons:
      - index: 13
        action:
          type: url
          url: https://example.com/info
"""
    path = tmp_path / "deck.yaml"
    path.write_text(yaml_text)
    cfg = load_deck_config(path)

    assert cfg.pages["main"].buttons[0].index == 13
    assert isinstance(cfg.pages["main"].buttons[0].action, UrlAction)


def test_loader_parses_text_style_for_text_only_button(tmp_path: Path) -> None:
    yaml_text = """
default_page: main
pages:
  main:
    buttons:
      - index: 0
        label: OpenAI
        text_style:
          background_color: "#102030"
          text_color: "#F0F0F0"
          bold: true
          italic: true
          underline: true
          font_family: Liberation Serif
          font_size: 34
"""
    path = tmp_path / "deck.yaml"
    path.write_text(yaml_text)
    cfg = load_deck_config(path)

    assert cfg.pages["main"].buttons[0].text_style == TextStyle(
        background_color="#102030",
        text_color="#F0F0F0",
        bold=True,
        italic=True,
        underline=True,
        font_family="Liberation Serif",
        font_size=34,
    )


def test_loader_accepts_legacy_single_page(tmp_path: Path) -> None:
    yaml_text = """
buttons:
  - index: 0
    label: A
    action: { type: shell, cmd: "echo hi" }
"""
    path = tmp_path / "deck.yaml"
    path.write_text(yaml_text)
    cfg = load_deck_config(path)

    assert cfg.default_page == "default"
    assert list(cfg.pages.keys()) == ["default"]
    page = cfg.pages["default"]
    assert len(page.buttons) == 1
    assert isinstance(page.buttons[0].action, ShellAction)


def test_loader_parses_predefined_command_action(tmp_path: Path) -> None:
    yaml_text = (
        "default_page: main\n"
        "pages:\n"
        "  main:\n"
        "    buttons:\n"
        "      - index: 5\n"
        "        action:\n"
        "          type: predefined_command\n"
        "          command_id: audio_mic_mute\n"
    )
    path = tmp_path / "deck.yaml"
    path.write_text(yaml_text)
    cfg = load_deck_config(path)

    action = cfg.pages["main"].buttons[0].action
    assert isinstance(action, PredefinedCommandAction)
    assert action.command_id == "audio_mic_mute"


# ---------------------------------------------------------------------- #
# Daemon tests                                                           #
# ---------------------------------------------------------------------- #


class FakeDeck(DeckDevice):
    """In-memory DeckDevice to exercise daemon paging without hardware."""

    def __init__(self) -> None:
        self._spec = DeckSpec(
            name="FakeDeck",
            usb_vendor_id=0x1234,
            usb_product_id=0x5678,
            button_count=13,
            button_rows=3,
            button_cols=5,
            icon_width=196,
            icon_height=196,
        )
        self.button_uploads: list[tuple[ButtonConfig, ...]] = []
        self.closed = False
        self.keep_alive_calls = 0
        self._queue: asyncio.Queue[ButtonEvent | DeviceInfoEvent] = asyncio.Queue()

    @property
    def spec(self) -> DeckSpec:
        return self._spec

    async def close(self) -> None:
        self.closed = True

    async def set_brightness(self, brightness: int, *, force: bool = False) -> None:
        pass

    async def keep_alive(self) -> None:
        self.keep_alive_calls += 1

    async def set_small_window_mode(self, mode: SmallWindowMode) -> None:
        pass

    async def set_small_window_data(
        self,
        *,
        cpu: int | None = 0,
        mem: int | None = 0,
        gpu: int | None = 0,
        time_str: str | None = None,
    ) -> None:
        pass

    async def set_buttons(self, configs, *, partial: bool = False) -> None:  # type: ignore[override]
        self.button_uploads.append(tuple(configs))

    def events(self) -> AsyncIterator[ButtonEvent | DeviceInfoEvent]:
        async def _iter() -> AsyncIterator[ButtonEvent | DeviceInfoEvent]:
            while True:
                yield await self._queue.get()

        return _iter()

    def inject_press(self, index: int) -> None:
        self._queue.put_nowait(
            ButtonEvent.create(index=index, pressed=True, state=0x00)
        )


class RecordingRunner:
    """Runner double that records accepted actions."""

    def __init__(self) -> None:
        self.actions: list[object] = []

    async def run(self, action: object) -> None:
        self.actions.append(action)


def _make_cfg() -> DeckConfig:
    return DeckConfig(
        pages={
            "main": Page(
                name="main",
                buttons=(
                    ButtonConfig(
                        index=0,
                        label="A",
                        action=ShellAction(type="shell", cmd="echo A"),
                    ),
                ),
            ),
            "media": Page(
                name="media",
                buttons=(
                    ButtonConfig(
                        index=0,
                        label="P",
                        action=ShellAction(type="shell", cmd="echo P"),
                    ),
                ),
            ),
        },
        fixed_buttons=(
            ButtonConfig(
                index=10,
                label="SwMain",
                action=SwitchPageAction(type="switch_page", page="main"),
            ),
            ButtonConfig(
                index=11,
                label="SwMedia",
                action=SwitchPageAction(type="switch_page", page="media"),
            ),
        ),
        default_page="main",
    )


@pytest.mark.asyncio
async def test_sync_layout_pushes_default_page_with_fixed_buttons() -> None:
    fake = FakeDeck()
    cfg = _make_cfg()

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg)
        await daemon.sync_layout()

    assert daemon.current_page == "main"
    assert len(fake.button_uploads) == 1
    uploaded_indices = [b.index for b in fake.button_uploads[0]]
    # main page button (0) + fixed buttons (10, 11)
    assert uploaded_indices == [0, 10, 11]


@pytest.mark.asyncio
async def test_sync_layout_skips_info_window_action_only_slot() -> None:
    fake = FakeDeck()
    cfg = DeckConfig(
        pages={
            "main": Page(
                name="main",
                buttons=(
                    ButtonConfig(index=0, label="A"),
                    ButtonConfig(
                        index=13,
                        action=UrlAction(type="url", url="https://example.com/info"),
                    ),
                ),
            )
        },
        default_page="main",
    )

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg)
        await daemon.sync_layout()

    uploaded_indices = [b.index for b in fake.button_uploads[0]]
    assert uploaded_indices == [0]


@pytest.mark.asyncio
async def test_switch_to_changes_page_and_reuploads() -> None:
    fake = FakeDeck()
    cfg = _make_cfg()

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg)
        await daemon.sync_layout()
        await daemon.switch_to("media")

    assert daemon.current_page == "media"
    assert len(fake.button_uploads) == 2
    second_labels = [b.label for b in fake.button_uploads[1]]
    assert "P" in second_labels  # media page button
    assert "SwMain" in second_labels  # fixed stayed
    assert "SwMedia" in second_labels


@pytest.mark.asyncio
async def test_switch_to_same_page_is_noop() -> None:
    fake = FakeDeck()
    cfg = _make_cfg()

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg)
        await daemon.sync_layout()
        await daemon.switch_to("main")

    # Only the initial sync — no redundant upload.
    assert len(fake.button_uploads) == 1


@pytest.mark.asyncio
async def test_switch_to_unknown_page_is_ignored() -> None:
    fake = FakeDeck()
    cfg = _make_cfg()

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg)
        await daemon.sync_layout()
        await daemon.switch_to("ghost")

    assert daemon.current_page == "main"
    assert len(fake.button_uploads) == 1


@pytest.mark.asyncio
async def test_event_loop_switches_page_on_fixed_button_press() -> None:
    fake = FakeDeck()
    cfg = _make_cfg()

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg)
        await daemon.sync_layout()

        stop = asyncio.Event()

        async def drive() -> None:
            fake.inject_press(11)  # SwMedia
            # Give the event loop a chance to process
            await asyncio.sleep(0.05)
            stop.set()

        await asyncio.gather(daemon.run(stop_event=stop), drive())

    assert daemon.current_page == "media"
    assert len(fake.button_uploads) == 2


@pytest.mark.asyncio
async def test_event_loop_logs_action_dispatch_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeDeck()
    cfg = _make_cfg()
    runner = RecordingRunner()
    info_calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        "ulanzi_linux.application.daemon.logger.info",
        lambda event, **kwargs: info_calls.append((event, kwargs)),
    )

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg, runner=runner)
        await daemon.sync_layout()

        stop = asyncio.Event()

        async def drive() -> None:
            fake.inject_press(0)
            await asyncio.sleep(0.05)
            stop.set()

        await asyncio.gather(daemon.run(stop_event=stop), drive())

    assert len(runner.actions) == 1
    assert isinstance(runner.actions[0], ShellAction)
    assert any(
        event == "button_event_received"
        and kwargs["index"] == 0
        and kwargs["pressed"] is True
        for event, kwargs in info_calls
    )
    assert any(
        event == "button_action_dispatch"
        and kwargs["action_type"] == "shell"
        and kwargs["cmd"] == "echo A"
        for event, kwargs in info_calls
    )
    assert any(
        event == "button_action_accepted"
        and kwargs["action_type"] == "shell"
        and kwargs["index"] == 0
        for event, kwargs in info_calls
    )
