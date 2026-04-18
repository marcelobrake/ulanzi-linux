"""Protocol command codes for the Ulanzi D200 HID communication.

These values are the inner 2-byte field of the 1024-byte HID frame. Prefix
``OUT_`` denotes a host-to-device command; ``IN_`` denotes a device-to-host
report. Values were extracted by reverse engineering (see docs/protocol.md).
"""

from __future__ import annotations

from enum import IntEnum


class OutgoingCommand(IntEnum):
    """Commands the host sends to the device."""

    SET_BUTTONS = 0x0001
    """Replace the entire button grid. Payload is a ZIP file."""

    PARTIALLY_UPDATE_BUTTONS = 0x000D
    """Update only some buttons. Same ZIP payload, additive semantics."""

    SET_SMALL_WINDOW_DATA = 0x0006
    """Update the status window (clock / CPU-MEM / background)."""

    SET_BRIGHTNESS = 0x000A
    """ASCII-encoded integer (0-100)."""

    SET_LABEL_STYLE = 0x000B
    """JSON payload with Align, Color, FontName, ShowTitle, Size, Weight."""


class IncomingCommand(IntEnum):
    """Reports the device sends to the host."""

    BUTTON = 0x0101
    """Button press/release event. Structured payload (see packet.py)."""

    DEVICE_INFO = 0x0303
    """Device info ASCII string emitted on handshake/heartbeat."""


class SmallWindowMode(IntEnum):
    """Display modes for the status window on the D200."""

    STATS = 0
    CLOCK = 1
    BACKGROUND = 2
