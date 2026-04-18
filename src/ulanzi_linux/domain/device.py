"""Abstract deck device interface.

This is the contract the application layer talks to. Concrete implementations
live in the infrastructure layer (e.g. UlanziD200Device).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass

from ulanzi_linux.domain.button_config import ButtonConfig
from ulanzi_linux.domain.commands import SmallWindowMode
from ulanzi_linux.domain.events import ButtonEvent, DeviceInfoEvent


@dataclass(frozen=True, slots=True)
class DeckSpec:
    """Physical characteristics of a deck model."""

    name: str
    usb_vendor_id: int
    usb_product_id: int
    button_count: int
    button_rows: int
    button_cols: int
    icon_width: int
    icon_height: int


class DeckDevice(ABC):
    """Abstract deck — the application layer only sees this interface."""

    @property
    @abstractmethod
    def spec(self) -> DeckSpec:
        """Return the physical specification of this deck."""

    @abstractmethod
    async def close(self) -> None:
        """Release the underlying transport and stop any background tasks."""

    @abstractmethod
    async def set_brightness(self, brightness: int, *, force: bool = False) -> None:
        """Set the LCD brightness.

        Args:
            brightness: Target brightness (0 to 100).
            force: Resend the command even if cached value matches.
        """

    @abstractmethod
    async def set_small_window_mode(self, mode: SmallWindowMode) -> None:
        """Change the status window display mode."""

    @abstractmethod
    async def set_small_window_data(
        self,
        *,
        cpu: int = 0,
        mem: int = 0,
        gpu: int = 0,
        time_str: str | None = None,
    ) -> None:
        """Push status window values."""

    @abstractmethod
    async def keep_alive(self) -> None:
        """Send a heartbeat so the firmware does not drop us back to standalone mode.

        The D200 firmware has a ~5 second watchdog — if no command arrives in
        that window it assumes the host is gone and reverts to the built-in
        'Ulanzi Studio' screen. Callers should invoke this on a timer.
        """

    @abstractmethod
    async def set_buttons(
        self, configs: Iterable[ButtonConfig], *, partial: bool = False
    ) -> None:
        """Upload icons and layout for the deck.

        Args:
            configs: ButtonConfig for each button to render.
            partial: If True use PARTIALLY_UPDATE_BUTTONS (additive) instead
                of SET_BUTTONS (replace grid).
        """

    @abstractmethod
    def events(self) -> AsyncIterator[ButtonEvent | DeviceInfoEvent]:
        """Async iterator over events coming from the device."""
