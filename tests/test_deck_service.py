"""Service-level tests using an in-memory fake device.

These exist to keep the application layer honest without needing the
physical deck attached.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import cast

import pytest

from ulanzi_linux.application.deck_service import DeckService
from ulanzi_linux.domain.button_config import ButtonConfig
from ulanzi_linux.domain.commands import SmallWindowMode
from ulanzi_linux.domain.device import DeckDevice, DeckSpec
from ulanzi_linux.domain.events import ButtonEvent, DeviceInfoEvent


class FakeDeck(DeckDevice):
    """In-memory DeckDevice used to exercise the application layer."""

    def __init__(self) -> None:
        self._spec = DeckSpec(
            name="FakeDeck",
            usb_vendor_id=0x1234,
            usb_product_id=0x5678,
            button_count=14,
            button_rows=3,
            button_cols=5,
            icon_width=85,
            icon_height=85,
        )
        self.brightness_calls: list[int] = []
        self.window_mode_calls: list[SmallWindowMode] = []
        self.closed = False
        self._queue: asyncio.Queue[ButtonEvent | DeviceInfoEvent] = asyncio.Queue()

    @property
    def spec(self) -> DeckSpec:
        return self._spec

    async def close(self) -> None:
        self.closed = True

    async def set_brightness(self, brightness: int, *, force: bool = False) -> None:
        self.brightness_calls.append(brightness)

    async def keep_alive(self) -> None:
        self.keep_alive_calls = getattr(self, "keep_alive_calls", 0) + 1

    async def set_small_window_mode(self, mode: SmallWindowMode) -> None:
        self.window_mode_calls.append(mode)

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
        self.button_uploads = list(configs)
        self.partial = partial

    def events(self) -> AsyncIterator[ButtonEvent | DeviceInfoEvent]:
        async def _iter() -> AsyncIterator[ButtonEvent | DeviceInfoEvent]:
            while True:
                yield await self._queue.get()

        return _iter()

    # Helpers for tests
    def inject_press(self, index: int) -> None:
        self._queue.put_nowait(
            ButtonEvent.create(index=index, pressed=True, state=0x00)
        )


@pytest.mark.asyncio
async def test_open_default_closes_device_on_exit() -> None:
    fake = FakeDeck()

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)):
        pass

    assert fake.closed is True


@pytest.mark.asyncio
async def test_set_brightness_delegates_to_device() -> None:
    fake = FakeDeck()

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        await svc.set_brightness(42)

    assert fake.brightness_calls == [42]


@pytest.mark.asyncio
async def test_listen_yields_injected_events() -> None:
    fake = FakeDeck()

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        fake.inject_press(4)
        async for event in svc.listen():
            assert isinstance(event, ButtonEvent)
            assert event.index == 4
            break  # only check the first event
