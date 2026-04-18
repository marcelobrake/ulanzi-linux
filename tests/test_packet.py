"""Round-trip and parse tests for the wire protocol struct.

These tests don't require any hardware — they exercise the construct
definitions directly with known byte patterns.
"""

from __future__ import annotations

import pytest

from ulanzi_linux.domain.commands import IncomingCommand, OutgoingCommand
from ulanzi_linux.infrastructure.packet import (
    HEADER_SIZE,
    MAX_PAYLOAD_SIZE,
    PACKET_SIZE,
    ButtonPressedStruct,
    IncomingPacketStruct,
    OutgoingPacketStruct,
)


class TestOutgoingPacket:
    def test_total_size_is_1024_bytes(self) -> None:
        payload = b"50"  # e.g. brightness ASCII payload
        built = OutgoingPacketStruct.build(
            {
                "command_protocol": int(OutgoingCommand.SET_BRIGHTNESS),
                "length": None,
                "data": payload,
            }
        )
        assert len(built) == PACKET_SIZE

    def test_magic_prefix_is_present(self) -> None:
        built = OutgoingPacketStruct.build(
            {
                "command_protocol": int(OutgoingCommand.SET_BRIGHTNESS),
                "length": None,
                "data": b"1",
            }
        )
        assert built[:2] == b"\x7c\x7c"

    def test_command_is_big_endian(self) -> None:
        built = OutgoingPacketStruct.build(
            {
                "command_protocol": int(OutgoingCommand.SET_BRIGHTNESS),
                "length": None,
                "data": b"",
            }
        )
        # SET_BRIGHTNESS = 0x000A ; big-endian bytes 3 and 4
        assert built[2:4] == b"\x00\x0A"

    def test_length_adapter_fills_data_length(self) -> None:
        payload = b"hello"
        built = OutgoingPacketStruct.build(
            {
                "command_protocol": int(OutgoingCommand.SET_BRIGHTNESS),
                "length": None,
                "data": payload,
            }
        )
        # Length is byte-swapped big-endian uint32, so 5 -> 05 00 00 00 on wire.
        assert built[4:8] == b"\x05\x00\x00\x00"

    def test_payload_is_padded_to_maximum(self) -> None:
        payload = b"50"
        built = OutgoingPacketStruct.build(
            {
                "command_protocol": int(OutgoingCommand.SET_BRIGHTNESS),
                "length": None,
                "data": payload,
            }
        )
        # Header + payload + padding must hit MAX_PAYLOAD_SIZE exactly.
        assert len(built) - HEADER_SIZE == MAX_PAYLOAD_SIZE
        # Tail must be zeros after the real payload.
        assert built[HEADER_SIZE + len(payload) :] == b"\x00" * (
            MAX_PAYLOAD_SIZE - len(payload)
        )


class TestIncomingPacket:
    def _build_raw_button_packet(
        self, *, index: int, pressed: bool, state: int = 0x00
    ) -> bytes:
        # Header: magic + command + byte-swapped length
        header = b"\x7c\x7c" + (int(IncomingCommand.BUTTON)).to_bytes(2, "big")
        length_wire = (4).to_bytes(4, "little")  # payload is 4 bytes
        # Payload: state, index, const 0x01, pressed byte
        payload = bytes([state, index, 0x01, 0x01 if pressed else 0x00])
        frame = header + length_wire + payload
        return frame.ljust(PACKET_SIZE, b"\x00")

    def test_parses_button_press_event(self) -> None:
        raw = self._build_raw_button_packet(index=7, pressed=True)
        parsed = IncomingPacketStruct.parse(raw)
        assert int(parsed.command_protocol) == int(IncomingCommand.BUTTON)
        assert parsed.data.index == 7
        assert parsed.data.pressed is True

    def test_parses_button_release_event(self) -> None:
        raw = self._build_raw_button_packet(index=3, pressed=False, state=0xFF)
        parsed = IncomingPacketStruct.parse(raw)
        assert parsed.data.index == 3
        assert parsed.data.pressed is False
        assert parsed.data.state == 0xFF


class TestButtonPayload:
    @pytest.mark.parametrize("pressed", [True, False])
    def test_pressed_flag_round_trips(self, pressed: bool) -> None:
        built = ButtonPressedStruct.build(
            {"state": 0x00, "index": 0, "pressed": pressed}
        )
        parsed = ButtonPressedStruct.parse(built)
        assert parsed.pressed is pressed
