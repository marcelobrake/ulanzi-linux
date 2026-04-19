"""Tests for HID path selection and open fallback logic."""

from __future__ import annotations

import pytest

from ulanzi_linux.infrastructure.hid_transport import (
    DeviceNotFoundError,
    DeviceOpenError,
    HidApiTransport,
)


class FakeHandle:
    def __init__(self, *, open_error: OSError | None = None) -> None:
        self.open_error = open_error
        self.opened_paths: list[bytes] = []
        self.nonblocking_values: list[bool] = []
        self.closed = False

    def open_path(self, path: bytes) -> None:
        self.opened_paths.append(path)
        if self.open_error is not None:
            raise self.open_error

    def open(self, _vendor_id: int, _product_id: int) -> None:
        if self.open_error is not None:
            raise self.open_error

    def set_nonblocking(self, value: bool) -> None:
        self.nonblocking_values.append(value)

    def close(self) -> None:
        self.closed = True


def test_open_tries_matching_paths_until_one_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handles = [
        FakeHandle(open_error=OSError("open failed")),
        FakeHandle(),
    ]

    monkeypatch.setattr(
        "ulanzi_linux.infrastructure.hid_transport.hid.enumerate",
        lambda: [
            {
                "vendor_id": 0x2207,
                "product_id": 0x0019,
                "interface_number": 0,
                "path": b"iface0",
            },
            {
                "vendor_id": 0x2207,
                "product_id": 0x0019,
                "interface_number": 1,
                "path": b"iface1",
            },
        ],
    )
    monkeypatch.setattr(
        "ulanzi_linux.infrastructure.hid_transport.hid.device",
        lambda: handles.pop(0),
    )

    transport = HidApiTransport.open(0x2207, 0x0019)

    assert isinstance(transport, HidApiTransport)
    assert handles == []


def test_open_raises_when_no_device_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ulanzi_linux.infrastructure.hid_transport.hid.enumerate",
        lambda: [],
    )

    with pytest.raises(DeviceNotFoundError):
        HidApiTransport.open(0x2207, 0x0019)


def test_open_raises_when_all_paths_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handles = [
        FakeHandle(open_error=OSError("iface0 failed")),
        FakeHandle(open_error=OSError("iface1 failed")),
    ]

    monkeypatch.setattr(
        "ulanzi_linux.infrastructure.hid_transport.hid.enumerate",
        lambda: [
            {
                "vendor_id": 0x2207,
                "product_id": 0x0019,
                "interface_number": 0,
                "path": b"iface0",
            },
            {
                "vendor_id": 0x2207,
                "product_id": 0x0019,
                "interface_number": 1,
                "path": b"iface1",
            },
        ],
    )
    monkeypatch.setattr(
        "ulanzi_linux.infrastructure.hid_transport.hid.device",
        lambda: handles.pop(0),
    )

    with pytest.raises(DeviceOpenError, match="iface0"):
        HidApiTransport.open(0x2207, 0x0019)