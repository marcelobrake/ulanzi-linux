"""Binary packet framing for the Ulanzi D200 HID protocol.

Frame layout (1024 bytes fixed length):
    [0x7C 0x7C][command:2B big-endian][length:4B byte-swapped BE][data:up to 1016B]

The ``length`` field is unusual: it is a 4-byte big-endian integer, but the
device reads it byte-swapped. We encode that quirk with construct's
``ByteSwapped(Int32ub)`` wrapper to match the on-wire representation.

References:
    - Ground truth behavior extracted from redphx/strmdck (MIT).
"""

from __future__ import annotations

from construct import (
    Adapter,
    Byte,
    Bytes,
    BytesInteger,
    ByteSwapped,
    Const,
    CString,
    ExprAdapter,
    GreedyBytes,
    Int32ub,
    Padded,
    Struct,
    Switch,
    this,
)

from ulanzi_linux.domain.commands import IncomingCommand

# Fixed on-wire frame size in bytes
PACKET_SIZE = 1024
# Header occupies 2 (magic) + 2 (command) + 4 (length) = 8 bytes
HEADER_SIZE = 8
# Maximum payload per frame
MAX_PAYLOAD_SIZE = PACKET_SIZE - HEADER_SIZE


class _LengthAdapter(Adapter):  # type: ignore[misc]
    """Fill the length field from context when ``None`` is passed on build."""

    def _encode(self, obj: int | None, context: dict, path: str) -> int:
        # If the caller passed None, infer length from the data blob
        return obj if obj is not None else len(context.data)

    def _decode(self, obj: int, context: dict, path: str) -> int:
        return obj


OutgoingPacketStruct = Struct(
    Const(b"\x7c\x7c"),
    "command_protocol" / BytesInteger(2),
    "length" / _LengthAdapter(ByteSwapped(Int32ub)),
    "data" / Padded(MAX_PAYLOAD_SIZE, GreedyBytes),
)
"""Struct for packets we send to the device."""


ButtonPressedStruct = Struct(
    "state" / Byte,
    "index" / Byte,
    Const(b"\x01"),
    "pressed"
    / ExprAdapter(
        Byte,
        # decoder: wire byte -> Python bool
        lambda obj, ctx: obj == 0x01,
        # encoder: Python bool -> wire byte
        lambda obj, ctx: 0x01 if obj else 0x00,
    ),
)
"""Inner payload of an IN_BUTTON packet."""


IncomingPacketStruct = Struct(
    Bytes(2),  # magic 0x7c 0x7c
    "command_protocol" / BytesInteger(2),
    "length" / ByteSwapped(Int32ub),
    "data"
    / Switch(
        this.command_protocol,
        {
            int(IncomingCommand.BUTTON): ButtonPressedStruct,
            int(IncomingCommand.DEVICE_INFO): CString("ascii"),
        },
    ),
)
"""Struct for packets we read from the device. Dispatches on command code."""
