"""Regression tests for automatic HID reconnection after a deck power-cycle."""

from __future__ import annotations

import asyncio

import pytest

from ulanzi_linux.domain.button_config import ButtonConfig
from ulanzi_linux.domain.commands import IncomingCommand, OutgoingCommand
from ulanzi_linux.domain.events import ButtonEvent
from ulanzi_linux.infrastructure.packet import PACKET_SIZE
from ulanzi_linux.infrastructure.ulanzi_d200 import UlanziD200Device


class FakeTransport:
    def __init__(
        self,
        *,
        read_results: list[bytes | None | Exception] | None = None,
        write_failures: int = 0,
    ) -> None:
        self.read_results = list(read_results or [])
        self.write_failures = write_failures
        self.writes: list[bytes] = []
        self.closed = False

    async def read(self, length: int) -> bytes | None:
        assert length == PACKET_SIZE
        if self.read_results:
            result = self.read_results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        await asyncio.sleep(0)
        return None

    async def write(self, packet: bytes) -> None:
        if self.write_failures > 0:
            self.write_failures -= 1
            raise OSError("device disconnected")
        self.writes.append(packet)

    async def close(self) -> None:
        self.closed = True


def _build_button_packet(*, index: int, pressed: bool, state: int = 0x00) -> bytes:
    header = b"\x7c\x7c" + int(IncomingCommand.BUTTON).to_bytes(2, "big")
    length_wire = (4).to_bytes(4, "little")
    payload = bytes([state, index, 0x01, 0x01 if pressed else 0x00])
    return (header + length_wire + payload).ljust(PACKET_SIZE, b"\x00")


def _framed_command_codes(writes: list[bytes]) -> list[int]:
    codes: list[int] = []
    for packet in writes:
        if packet[:3] != b"\x00\x7c\x7c":
            continue
        codes.append(int.from_bytes(packet[3:5], "big"))
    return codes


def _framed_payloads(writes: list[bytes]) -> list[bytes]:
    payloads: list[bytes] = []
    for packet in writes:
        if packet[:3] != b"\x00\x7c\x7c":
            continue
        payloads.append(packet[9:].rstrip(b"\x00"))
    return payloads


@pytest.mark.asyncio
async def test_write_failure_reconnects_and_replays_cached_state() -> None:
    first = FakeTransport()
    second = FakeTransport()
    factory_calls = 0

    def factory() -> FakeTransport:
        nonlocal factory_calls
        factory_calls += 1
        return second

    device = UlanziD200Device(
        first,
        transport_factory=factory,
        reconnect_poll_interval_s=0.001,
    )

    await device.set_brightness(42)
    await device.set_buttons((ButtonConfig(index=0, label="A"),))

    first.write_failures = 1
    await device.set_small_window_data(cpu=11, mem=22, gpu=0, time_str="18:42")
    await device.close()

    assert factory_calls == 1
    assert first.closed is True
    codes = _framed_command_codes(second.writes)
    assert int(OutgoingCommand.SET_BRIGHTNESS) in codes
    assert int(OutgoingCommand.SET_BUTTONS) in codes
    assert int(OutgoingCommand.SET_SMALL_WINDOW_DATA) in codes
    assert b"1|11|22|18:42|0" in _framed_payloads(second.writes)


@pytest.mark.asyncio
async def test_read_loop_reconnects_and_resumes_events() -> None:
    first = FakeTransport(read_results=[OSError("device disappeared")])
    second = FakeTransport(
        read_results=[_build_button_packet(index=4, pressed=True)]
    )
    factory_calls = 0

    def factory() -> FakeTransport:
        nonlocal factory_calls
        factory_calls += 1
        return second

    device = UlanziD200Device(
        first,
        transport_factory=factory,
        reconnect_poll_interval_s=0.001,
    )
    device._start_read_loop()

    async def next_event() -> ButtonEvent:
        async for event in device.events():
            if isinstance(event, ButtonEvent):
                return event
        raise AssertionError("event stream ended unexpectedly")

    event = await asyncio.wait_for(next_event(), timeout=0.5)
    await device.close()

    assert factory_calls == 1
    assert first.closed is True
    assert event.index == 4
    assert event.pressed is True