"""Domain events emitted by a connected deck.

Events are immutable value objects that flow from the infrastructure layer
upward to the application layer, without any framework or transport coupling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class ButtonEvent:
    """A physical button was pressed or released.

    Attributes:
        index: Zero-based button index as reported by the device (0 to
            BUTTON_COUNT-1). The D200 uses a 3x5 grid with 13 active buttons.
        pressed: True if the event is a press, False if a release.
        state: The device-reported internal state byte. Meaning is
            firmware-dependent; stored for observability.
        occurred_at: UTC timestamp captured by the host when the event arrived.
    """

    index: int
    pressed: bool
    state: int
    occurred_at: datetime

    @classmethod
    def create(cls, index: int, pressed: bool, state: int) -> ButtonEvent:
        """Create a ButtonEvent stamped with the current UTC time."""
        return cls(
            index=index,
            pressed=pressed,
            state=state,
            occurred_at=datetime.now(tz=timezone.utc),
        )


@dataclass(frozen=True, slots=True)
class DeviceInfoEvent:
    """Device reported its identity string. Usually on connect or heartbeat."""

    info: str
    occurred_at: datetime

    @classmethod
    def create(cls, info: str) -> DeviceInfoEvent:
        """Create a DeviceInfoEvent stamped with the current UTC time."""
        return cls(info=info, occurred_at=datetime.now(tz=timezone.utc))
