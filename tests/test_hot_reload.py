"""Tests for DeckDaemon.reload_config — atomic YAML swap semantics.

Covers:
    * Reload preserves the current page when it still exists.
    * Reload falls back to default when the current page is gone.
    * Broken YAML leaves the previous config in place (no bricking).
    * Integration: watcher + daemon end-to-end from a file edit.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest

from ulanzi_linux.application.config_watcher import ConfigWatcher
from ulanzi_linux.application.daemon import DeckDaemon
from ulanzi_linux.application.deck_service import DeckService
from ulanzi_linux.domain.button_config import (
    ButtonConfig,
    DeckConfig,
    Page,
    ShellAction,
)
from ulanzi_linux.domain.commands import SmallWindowMode
from ulanzi_linux.domain.device import DeckDevice, DeckSpec
from ulanzi_linux.domain.events import ButtonEvent, DeviceInfoEvent


class FakeDeck(DeckDevice):
    """Minimal DeckDevice double — mirrors tests/test_pagination FakeDeck."""

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
        self._queue: asyncio.Queue[ButtonEvent | DeviceInfoEvent] = asyncio.Queue()

    @property
    def spec(self) -> DeckSpec:
        return self._spec

    async def close(self) -> None:
        pass

    async def set_brightness(self, brightness: int, *, force: bool = False) -> None:
        pass

    async def keep_alive(self) -> None:
        pass

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


def _cfg_with_pages(*pages: str, default: str) -> DeckConfig:
    return DeckConfig(
        pages={
            name: Page(
                name=name,
                buttons=(
                    ButtonConfig(
                        index=0,
                        label=name.upper(),
                        action=ShellAction(type="shell", cmd=f"echo {name}"),
                    ),
                ),
            )
            for name in pages
        },
        default_page=default,
    )


def _write(path: Path, text: str) -> None:
    path.write_text(text)


# ---------------------------------------------------------------------- #
# Direct reload_config tests                                             #
# ---------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_reload_preserves_current_page(tmp_path: Path) -> None:
    fake = FakeDeck()
    initial = _cfg_with_pages("main", "media", default="main")

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, initial)
        await daemon.sync_layout()
        await daemon.switch_to("media")

        # New YAML still contains "media", with an added "dev" page.
        yaml_path = tmp_path / "deck.yaml"
        _write(
            yaml_path,
            """
default_page: main
pages:
  main:
    buttons:
      - index: 0
        label: M
  media:
    buttons:
      - index: 0
        label: P
  dev:
    buttons:
      - index: 0
        label: D
""",
        )
        await daemon.reload_config(yaml_path)

    assert daemon.current_page == "media"  # preserved
    assert set(daemon.config.pages.keys()) == {"main", "media", "dev"}
    # Initial sync + switch_to("media") + reload push = 3 uploads.
    assert len(fake.button_uploads) == 3


@pytest.mark.asyncio
async def test_reload_falls_back_to_default_when_page_gone(tmp_path: Path) -> None:
    fake = FakeDeck()
    initial = _cfg_with_pages("main", "media", default="main")

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, initial)
        await daemon.sync_layout()
        await daemon.switch_to("media")

        yaml_path = tmp_path / "deck.yaml"
        _write(
            yaml_path,
            """
default_page: home
pages:
  home:
    buttons:
      - index: 0
        label: H
""",
        )
        await daemon.reload_config(yaml_path)

    assert daemon.current_page == "home"  # fell back to new default
    assert list(daemon.config.pages.keys()) == ["home"]


@pytest.mark.asyncio
async def test_reload_ignores_broken_yaml(tmp_path: Path) -> None:
    fake = FakeDeck()
    initial = _cfg_with_pages("main", default="main")

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, initial)
        await daemon.sync_layout()

        yaml_path = tmp_path / "deck.yaml"
        _write(yaml_path, "pages:\n  broken:\n    buttons: [{garbage]")
        await daemon.reload_config(yaml_path)

    # Previous config stays intact; no extra push happened.
    assert daemon.current_page == "main"
    assert list(daemon.config.pages.keys()) == ["main"]
    assert len(fake.button_uploads) == 1


# ---------------------------------------------------------------------- #
# Integration: watcher drives reload end-to-end                          #
# ---------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_watcher_triggers_reload_on_edit(tmp_path: Path) -> None:
    fake = FakeDeck()
    yaml_path = tmp_path / "deck.yaml"
    _write(
        yaml_path,
        """
default_page: main
pages:
  main:
    buttons:
      - index: 0
        label: A
""",
    )

    # Load initial config from disk so paths line up with the watcher.
    from ulanzi_linux.application.config_loader import load_deck_config

    cfg = load_deck_config(yaml_path)

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg)
        await daemon.sync_layout()

        watcher = ConfigWatcher(
            yaml_path, on_change=daemon.reload_config, poll_interval_s=0.05
        )
        stop = asyncio.Event()

        async def _edit_then_stop() -> None:
            await asyncio.sleep(0.15)
            _write(
                yaml_path,
                """
default_page: main
pages:
  main:
    buttons:
      - index: 0
        label: A
      - index: 1
        label: B
""",
            )
            # Give the watcher a couple of ticks to observe + reload.
            await asyncio.sleep(0.5)
            stop.set()

        await asyncio.gather(
            daemon.run(stop_event=stop, watcher=watcher),
            _edit_then_stop(),
        )

    # After reload "main" now has 2 buttons — verify the push reflects that.
    labels_per_push = [[b.label for b in up] for up in fake.button_uploads]
    assert ["A"] in labels_per_push  # initial sync
    assert any({"A", "B"}.issubset(set(labels)) for labels in labels_per_push)
