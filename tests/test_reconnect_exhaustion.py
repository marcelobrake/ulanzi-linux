"""The reconnect loop must give up instead of polling a dead context forever.

python-hidapi cannot reset its library context in-process, so a handle
invalidated by an unplug can leave the daemon permanently unable to enumerate
the deck — while a freshly started process finds it immediately. Retrying
forever therefore hangs instead of recovering; the daemon has to exit so its
supervisor can hand it a clean context.
"""

from __future__ import annotations

import pytest

from ulanzi_linux.infrastructure.hid_transport import (
    DeviceNotFoundError,
    TransportReconnectExhaustedError,
)
from ulanzi_linux.infrastructure.ulanzi_d200 import UlanziD200Device


class DeadTransport:
    """Already unplugged: every write fails, which is what triggers recovery."""

    def __init__(self) -> None:
        self.closed = False

    async def read(self, length: int) -> bytes | None:
        return None

    async def write(self, packet: bytes) -> None:
        raise OSError("device disconnected")

    async def close(self) -> None:
        self.closed = True


class WorkingTransport:
    """A healthy transport, so a reconnect can actually complete."""

    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    async def read(self, length: int) -> bytes | None:
        return None

    async def write(self, packet: bytes) -> None:
        self.writes.append(packet)

    async def close(self) -> None:
        self.closed = True


def _missing() -> WorkingTransport:
    raise DeviceNotFoundError("No HID device found for 0x2207:0x0019")


@pytest.mark.asyncio
async def test_reconnect_gives_up_after_the_attempt_budget() -> None:
    """A deck that never returns must not spin forever — it must raise."""
    attempts = 0

    def never_returns() -> WorkingTransport:
        nonlocal attempts
        attempts += 1
        return _missing()

    device = UlanziD200Device(
        DeadTransport(),
        transport_factory=never_returns,
        reconnect_poll_interval_s=0,
        max_reconnect_attempts=3,
    )

    with pytest.raises(TransportReconnectExhaustedError):
        await device.set_brightness(50)

    assert attempts == 3


@pytest.mark.asyncio
async def test_successful_reconnect_does_not_raise() -> None:
    """A deck that comes back within budget reconnects silently."""
    attempts = 0
    healthy = WorkingTransport()

    def back_on_second_try() -> WorkingTransport:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            return _missing()
        return healthy

    device = UlanziD200Device(
        DeadTransport(),
        transport_factory=back_on_second_try,
        reconnect_poll_interval_s=0,
        max_reconnect_attempts=10,
    )

    await device.set_brightness(50)

    assert attempts == 2


@pytest.mark.asyncio
async def test_zero_budget_opts_back_into_unbounded_retries() -> None:
    """``<= 0`` preserves the previous forever-polling behaviour."""
    attempts = 0
    healthy = WorkingTransport()

    def back_on_fifth_try() -> WorkingTransport:
        nonlocal attempts
        attempts += 1
        if attempts < 5:
            return _missing()
        return healthy

    device = UlanziD200Device(
        DeadTransport(),
        transport_factory=back_on_fifth_try,
        reconnect_poll_interval_s=0,
        max_reconnect_attempts=0,
    )

    # Recovers on the 5th attempt — past any bounded budget we would have set.
    await device.set_brightness(50)

    assert attempts == 5
