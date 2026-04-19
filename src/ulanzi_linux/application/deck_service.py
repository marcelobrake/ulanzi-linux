"""Application service that orchestrates high-level deck use cases.

The service is deliberately thin — it coordinates domain objects and the
infrastructure layer without leaking HID / packet details upward.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TypeAlias

import structlog

from ulanzi_linux.domain.commands import SmallWindowMode
from ulanzi_linux.domain.device import DeckDevice, DeckSpec
from ulanzi_linux.domain.events import ButtonEvent, DeviceInfoEvent
from ulanzi_linux.infrastructure.ulanzi_d200 import UlanziD200Device

logger = structlog.get_logger(__name__)

# Function shape for a device factory — useful for tests to inject a fake.
DeviceFactory: TypeAlias = Callable[[], DeckDevice]


class DeckService:
    """High-level use cases against a deck device.

    This class is the single place the UI layers (CLI, future GUI, daemon)
    should talk to. Keeping logic here instead of in the CLI makes all
    entry points equivalent and testable.
    """

    def __init__(self, device: DeckDevice) -> None:
        self._device = device

    # ------------------------------------------------------------------ #
    # Lifecycle helpers                                                   #
    # ------------------------------------------------------------------ #

    @classmethod
    @asynccontextmanager
    async def open_default(
        cls, factory: DeviceFactory = UlanziD200Device.open
    ) -> AsyncIterator[DeckService]:
        """Open the default D200 and guarantee cleanup on exit."""
        device = factory()
        service = cls(device)
        try:
            yield service
        finally:
            await device.close()

    # ------------------------------------------------------------------ #
    # Queries                                                             #
    # ------------------------------------------------------------------ #

    @property
    def spec(self) -> DeckSpec:
        return self._device.spec

    # ------------------------------------------------------------------ #
    # Commands                                                            #
    # ------------------------------------------------------------------ #

    async def set_brightness(self, brightness: int) -> None:
        """Clamp-free setter — domain validation lives in the device."""
        await self._device.set_brightness(brightness)

    async def set_small_window_mode(self, mode: SmallWindowMode) -> None:
        await self._device.set_small_window_mode(mode)

    async def push_small_window_stats(
        self, *, cpu: int | None, mem: int | None, gpu: int | None = 0
    ) -> None:
        await self._device.set_small_window_data(cpu=cpu, mem=mem, gpu=gpu)

    # ------------------------------------------------------------------ #
    # Reactive stream                                                     #
    # ------------------------------------------------------------------ #

    async def listen(
        self,
    ) -> AsyncIterator[ButtonEvent | DeviceInfoEvent]:
        """Yield events as they arrive from the deck."""
        logger.info("listening_started", deck=self._device.spec.name)
        async for event in self._device.events():
            yield event


__all__ = ["DeckService", "DeviceFactory"]
