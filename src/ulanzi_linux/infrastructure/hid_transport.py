"""HID transport layer wrapping python-hidapi.

Provides an async-friendly wrapper over the blocking ``hid.device`` API,
so the rest of the codebase can use ``asyncio`` naturally.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any, Protocol

import hid  # type: ignore[import-untyped]
import structlog

logger = structlog.get_logger(__name__)


class HidTransport(Protocol):
    """Minimal HID transport contract so tests can swap a fake in."""

    async def read(self, length: int) -> bytes | None:
        """Non-blocking read. Returns ``None`` if no data is ready."""

    async def write(self, packet: bytes) -> None:
        """Write a single HID output packet."""

    async def close(self) -> None:
        """Close the underlying device handle."""


class HidApiTransport:
    """Concrete HID transport backed by python-hidapi."""

    def __init__(self, device: Any) -> None:
        self._device = device
        self._lock = asyncio.Lock()

    @classmethod
    def open(cls, vendor_id: int, product_id: int) -> HidApiTransport:
        """Open the first HID device matching VID/PID.

        Args:
            vendor_id: USB vendor ID to match.
            product_id: USB product ID to match.

        Raises:
            DeviceNotFoundError: No matching device is connected.
            DeviceOpenError: The device was found but could not be opened.
        """
        matches = sorted(
            enumerate_hid_devices(vendor_id=vendor_id, product_id=product_id),
            key=lambda entry: (
                entry.get("interface_number") != 0,
                entry.get("interface_number") is None,
                entry.get("interface_number")
                if isinstance(entry.get("interface_number"), int)
                else 1_000_000,
            ),
        )
        if not matches:
            raise DeviceNotFoundError(
                f"No HID device found for {vendor_id:#06x}:{product_id:#06x}"
            )

        errors: list[str] = []
        for entry in matches:
            handle = hid.device()
            path = entry.get("path")
            try:
                if path:
                    handle.open_path(path)
                else:
                    handle.open(vendor_id, product_id)
                handle.set_nonblocking(True)
                logger.info(
                    "hid_device_opened",
                    vendor_id=f"{vendor_id:#06x}",
                    product_id=f"{product_id:#06x}",
                    interface_number=entry.get("interface_number"),
                    path=path.decode("utf-8", errors="replace")
                    if isinstance(path, bytes)
                    else str(path),
                )
                return cls(handle)
            except OSError as exc:
                errors.append(
                    "interface="
                    f"{entry.get('interface_number', '?')}"
                    f" path={path!r} error={exc}"
                )
                try:
                    handle.close()
                except Exception:  # noqa: BLE001
                    pass

        raise DeviceOpenError(
            f"Failed to open any device for {vendor_id:#06x}:{product_id:#06x}: "
            + "; ".join(errors)
        )

    async def read(self, length: int) -> bytes | None:
        """Perform a non-blocking HID read. Returns ``None`` if no data."""
        # hid.device.read returns an empty list when non-blocking and no data
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, self._device.read, length)
        if not raw:
            return None
        return bytes(raw)

    async def write(self, packet: bytes) -> None:
        """Write a single HID output packet, serialized across callers."""
        async with self._lock:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._device.write, packet)

    async def close(self) -> None:
        """Close the underlying device. Safe to call multiple times."""
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._device.close)
            logger.info("hid_device_closed")
        except Exception as exc:  # noqa: BLE001 — best effort
            logger.warning("hid_close_failed", error=str(exc))


class DeviceNotFoundError(RuntimeError):
    """No matching device is connected."""


class DeviceOpenError(RuntimeError):
    """A device matching VID/PID was found but could not be opened."""


def enumerate_hid_devices(
    vendor_id: int | None = None,
    product_id: int | None = None,
) -> Iterable[dict[str, Any]]:
    """Enumerate connected HID devices, optionally filtered by VID/PID.

    Args:
        vendor_id: If provided, only return devices matching this VID.
        product_id: If provided, only return devices matching this PID.

    Yields:
        One dict per matching device with standard hidapi fields
        (vendor_id, product_id, path, manufacturer_string, product_string, etc.).
    """
    for entry in hid.enumerate():
        if vendor_id is not None and entry.get("vendor_id") != vendor_id:
            continue
        if product_id is not None and entry.get("product_id") != product_id:
            continue
        yield entry
