"""Concrete DeckDevice implementation for the Ulanzi Stream Pad D200.

This class is the glue between the raw HID transport, the binary packet
framing, and the high-level domain commands the application layer expects.

Design notes:
    * The read loop runs as a dedicated asyncio task and pushes parsed
      events into an ``asyncio.Queue`` consumed by ``events()``. Keeping the
      loop decoupled from consumers means a slow consumer cannot stall the
      device.
    * Writes are serialized inside the transport, so concurrent callers
      (CLI + background service) are safe.
    * State the device is known to hold (brightness, small-window mode)
      is cached to avoid re-sending no-op commands over a slow USB bus.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Iterable
from typing import Final, TypeAlias

import structlog

from ulanzi_linux.domain.button_config import ButtonConfig
from ulanzi_linux.domain.commands import (
    IncomingCommand,
    OutgoingCommand,
    SmallWindowMode,
)
from ulanzi_linux.domain.device import DeckDevice, DeckSpec
from ulanzi_linux.domain.events import ButtonEvent, DeviceInfoEvent
from ulanzi_linux.infrastructure.hid_transport import (
    DeviceNotFoundError,
    DeviceOpenError,
    HidApiTransport,
    HidTransport,
    enumerate_hid_devices,
)
from ulanzi_linux.infrastructure.packet import (
    MAX_PAYLOAD_SIZE,
    PACKET_SIZE,
    ButtonPressedStruct,
    IncomingPacketStruct,
    OutgoingPacketStruct,
)
from ulanzi_linux.infrastructure.zip_builder import build_buttons_zip

logger = structlog.get_logger(__name__)

TransportFactory: TypeAlias = Callable[[], HidTransport]

DEFAULT_RECONNECT_POLL_INTERVAL_S: float = 1.0

DEFAULT_LABEL_STYLE: Final[dict[str, object]] = {
    "Align": "bottom",
    "Color": 0xFFFFFF,
    "FontName": "Roboto",
    "ShowTitle": True,
    "Size": 10,
    "Weight": 80,
}


# Physical specification of the Ulanzi Stream Pad D200.
# VID/PID and grid confirmed against real hardware (Zkswe/ulanzi).
D200_SPEC: Final[DeckSpec] = DeckSpec(
    name="Ulanzi Stream Pad D200",
    usb_vendor_id=0x2207,
    usb_product_id=0x0019,
    button_count=13,
    button_rows=3,
    button_cols=5,
    icon_width=196,
    icon_height=196,
)


class UlanziD200Device(DeckDevice):
    """Concrete deck implementation for the Ulanzi Stream Pad D200."""

    def __init__(
        self,
        transport: HidTransport,
        *,
        transport_factory: TransportFactory | None = None,
        reconnect_poll_interval_s: float = DEFAULT_RECONNECT_POLL_INTERVAL_S,
    ) -> None:
        self._transport: HidTransport | None = transport
        self._transport_factory = transport_factory or self._open_transport
        self._reconnect_poll_interval_s = reconnect_poll_interval_s
        self._spec = D200_SPEC
        self._event_queue: asyncio.Queue[ButtonEvent | DeviceInfoEvent] = (
            asyncio.Queue(maxsize=256)
        )
        self._read_task: asyncio.Task[None] | None = None
        self._closed = False
        self._reconnect_lock = asyncio.Lock()

        # Cached state — avoid redundant writes to a slow USB bus.
        self._cached_brightness: int | None = None
        self._cached_small_window_mode: SmallWindowMode | None = None
        self._last_small_window_data: tuple[
            int | None, int | None, int | None, str | None
        ] | None = None
        self._label_style_applied = False
        self._button_state: dict[int, ButtonConfig] = {}
        self._button_state_is_full = False

    # ------------------------------------------------------------------ #
    # Construction                                                        #
    # ------------------------------------------------------------------ #

    @classmethod
    def open(cls) -> UlanziD200Device:
        """Open the first D200 attached to the system.

        Raises:
            DeviceNotFoundError: No matching device was detected.
            DeviceOpenError: A device was found but cannot be opened
                (permissions, busy, etc.).
        """
        matches = list(
            enumerate_hid_devices(
                vendor_id=D200_SPEC.usb_vendor_id,
                product_id=D200_SPEC.usb_product_id,
            )
        )
        if not matches:
            raise DeviceNotFoundError(
                f"No Ulanzi D200 found (VID={D200_SPEC.usb_vendor_id:#06x}, "
                f"PID={D200_SPEC.usb_product_id:#06x}). Is the device plugged in?"
            )

        transport = cls._open_transport()
        device = cls(transport, transport_factory=cls._open_transport)
        device._start_read_loop()
        logger.info(
            "d200_opened",
            matches=len(matches),
            vendor_id=f"{D200_SPEC.usb_vendor_id:#06x}",
            product_id=f"{D200_SPEC.usb_product_id:#06x}",
        )
        return device

    @staticmethod
    def _open_transport() -> HidTransport:
        return HidApiTransport.open(
            D200_SPEC.usb_vendor_id, D200_SPEC.usb_product_id
        )

    # ------------------------------------------------------------------ #
    # DeckDevice contract                                                 #
    # ------------------------------------------------------------------ #

    @property
    def spec(self) -> DeckSpec:
        return self._spec

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        transport = self._transport
        self._transport = None
        if self._read_task is not None:
            self._read_task.cancel()
            try:
                await self._read_task
            except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
                if not isinstance(exc, asyncio.CancelledError):
                    logger.warning("read_loop_shutdown_error", error=str(exc))
        if transport is not None:
            await transport.close()
        logger.info("d200_closed")

    async def set_brightness(self, brightness: int, *, force: bool = False) -> None:
        if not 0 <= brightness <= 100:
            raise ValueError(f"brightness must be in 0..100, got {brightness}")

        if not force and self._cached_brightness == brightness:
            logger.debug("set_brightness_skipped", brightness=brightness)
            return

        self._cached_brightness = brightness
        # Protocol quirk: brightness is sent as an ASCII string, not a byte.
        payload = str(brightness).encode("ascii")
        await self._send(OutgoingCommand.SET_BRIGHTNESS, payload)
        logger.info("brightness_set", brightness=brightness)

    async def keep_alive(self) -> None:
        # Any outbound command would satisfy the watchdog; strmdck uses
        # SET_SMALL_WINDOW_DATA because it is idempotent and cheap.
        if self._last_small_window_data is not None:
            cpu, mem, gpu, time_str = self._last_small_window_data
            await self.set_small_window_data(
                cpu=cpu,
                mem=mem,
                gpu=gpu,
                time_str=time_str,
            )
        elif self._cached_small_window_mode is not None:
            await self._send(
                OutgoingCommand.SET_SMALL_WINDOW_DATA,
                self._build_small_window_payload(
                    mode=self._cached_small_window_mode,
                    cpu=None,
                    mem=None,
                    gpu=None,
                    time_str=None,
                ),
            )
        else:
            await self._send(OutgoingCommand.SET_SMALL_WINDOW_DATA, b"")
        logger.debug("keep_alive_sent")

    async def set_small_window_mode(self, mode: SmallWindowMode) -> None:
        self._cached_small_window_mode = mode
        if mode != SmallWindowMode.BACKGROUND and self._last_small_window_data is None:
            logger.info("small_window_mode_set", mode=mode.name, deferred=True)
            return
        if self._last_small_window_data is not None:
            cpu, mem, gpu, time_str = self._last_small_window_data
        else:
            cpu, mem, gpu, time_str = None, None, None, None
        await self._send(
            OutgoingCommand.SET_SMALL_WINDOW_DATA,
            self._build_small_window_payload(
                mode=mode,
                cpu=cpu,
                mem=mem,
                gpu=gpu,
                time_str=time_str,
            ),
        )
        logger.info("small_window_mode_set", mode=mode.name)

    async def set_small_window_data(
        self,
        *,
        cpu: int | None = 0,
        mem: int | None = 0,
        gpu: int | None = 0,
        time_str: str | None = None,
    ) -> None:
        mode = self._cached_small_window_mode or SmallWindowMode.CLOCK
        self._last_small_window_data = (cpu, mem, gpu, time_str)
        payload = self._build_small_window_payload(
            mode=mode,
            cpu=cpu,
            mem=mem,
            gpu=gpu,
            time_str=time_str,
        )
        await self._send(OutgoingCommand.SET_SMALL_WINDOW_DATA, payload)
        logger.info("small_window_data_set", cpu=cpu, mem=mem, gpu=gpu)

    async def set_buttons(
        self, configs: Iterable[ButtonConfig], *, partial: bool = False
    ) -> None:
        configs_tuple = tuple(configs)
        self._remember_buttons(configs_tuple, partial=partial)
        await self._ensure_label_style()
        blob = build_buttons_zip(configs_tuple, fill_missing=not partial)
        command = (
            OutgoingCommand.PARTIALLY_UPDATE_BUTTONS
            if partial
            else OutgoingCommand.SET_BUTTONS
        )
        await self._send_chunked(command, blob)
        logger.info("buttons_uploaded", size=len(blob), partial=partial)

    def events(self) -> AsyncIterator[ButtonEvent | DeviceInfoEvent]:
        return self._event_iterator()

    # ------------------------------------------------------------------ #
    # Internals                                                           #
    # ------------------------------------------------------------------ #

    async def _send_chunked(self, command: OutgoingCommand, blob: bytes) -> None:
        transport = await self._require_transport()
        try:
            await self._send_chunked_raw(transport, command, blob)
        except Exception as exc:  # noqa: BLE001
            await self._recover_transport(
                failed_transport=transport,
                operation=f"write_{command.name.lower()}",
                error=exc,
            )

    async def _send_chunked_raw(
        self, transport: HidTransport, command: OutgoingCommand, blob: bytes
    ) -> None:
        """Stream a payload across multiple 1024-byte HID frames.

        Wire protocol (ground truth from redphx/strmdck):
            * Frame 0: full header ``[0x7C 0x7C][command][length=total_size]``
              followed by the first ``MAX_PAYLOAD_SIZE`` (1016) bytes of the
              blob. Length field holds the *entire* blob size, not the chunk.
            * Frames 1..N: RAW 1024-byte chunks with NO header wrapping.
              Firmware keeps appending bytes until ``length`` is satisfied.

        A mistake here — e.g. wrapping every chunk in PacketStruct — corrupts
        the firmware's parser state and wedges the device into a black-screen
        mode that only a power cycle recovers from.
        """
        total = len(blob)

        # First frame: header + first 1016-byte slice, padded to 1024.
        first_chunk = blob[:MAX_PAYLOAD_SIZE]
        first_frame = OutgoingPacketStruct.build(
            {
                "command_protocol": int(command),
                "length": total,
                "data": first_chunk,
            }
        )
        assert len(first_frame) == PACKET_SIZE, (
            f"first frame must be {PACKET_SIZE} bytes, got {len(first_frame)}"
        )
        await transport.write(b"\x00" + first_frame)
        logger.debug(
            "chunk_sent",
            command=command.name,
            chunk=0,
            size=len(first_chunk),
            total=total,
            framed=True,
        )

        # Continuation frames: raw 1024-byte chunks, zero-padded if short.
        sent = len(first_chunk)
        chunk_index = 1
        for offset in range(MAX_PAYLOAD_SIZE, total, PACKET_SIZE):
            chunk = blob[offset : offset + PACKET_SIZE]
            padded = chunk.ljust(PACKET_SIZE, b"\x00")
            await transport.write(b"\x00" + padded)
            sent += len(chunk)
            logger.debug(
                "chunk_sent",
                command=command.name,
                chunk=chunk_index,
                size=len(chunk),
                total=total,
                framed=False,
            )
            chunk_index += 1

    async def _send(self, command: OutgoingCommand, data: bytes) -> None:
        transport = await self._require_transport()
        try:
            await self._send_raw(transport, command, data)
        except Exception as exc:  # noqa: BLE001
            await self._recover_transport(
                failed_transport=transport,
                operation=f"write_{command.name.lower()}",
                error=exc,
            )

    async def _send_raw(
        self, transport: HidTransport, command: OutgoingCommand, data: bytes
    ) -> None:
        frame = OutgoingPacketStruct.build(
            {"command_protocol": int(command), "length": None, "data": data}
        )
        assert len(frame) == PACKET_SIZE, (
            f"outgoing frame must be exactly {PACKET_SIZE} bytes, got {len(frame)}"
        )
        # python-hidapi convention: prepend a Report ID byte (0x00).
        packet = b"\x00" + frame
        await transport.write(packet)
        logger.debug(
            "packet_sent",
            command=command.name,
            command_code=f"{int(command):#06x}",
            payload_size=len(data),
        )

    def _start_read_loop(self) -> None:
        loop = asyncio.get_event_loop()
        self._read_task = loop.create_task(
            self._read_loop(), name="ulanzi_d200_read_loop"
        )

    async def _read_loop(self) -> None:
        logger.info("read_loop_started")
        try:
            while not self._closed:
                transport = await self._require_transport()
                try:
                    raw = await transport.read(PACKET_SIZE)
                except Exception as exc:  # noqa: BLE001
                    await self._recover_transport(
                        failed_transport=transport,
                        operation="read_packet",
                        error=exc,
                    )
                    continue
                if raw is None:
                    # Non-blocking read returned nothing — yield and retry.
                    await asyncio.sleep(0.001)
                    continue
                if len(raw) < 8:
                    logger.warning("short_packet_ignored", size=len(raw))
                    continue
                self._dispatch_incoming(raw)
        except asyncio.CancelledError:
            logger.info("read_loop_cancelled")
            raise
        except Exception as exc:  # noqa: BLE001
            # Surface unexpected errors but keep the coroutine from crashing
            # the whole event loop.
            logger.error("read_loop_error", error=str(exc), exc_info=True)
            raise

    def _dispatch_incoming(self, raw: bytes) -> None:
        try:
            parsed = IncomingPacketStruct.parse(raw)
        except Exception as exc:  # noqa: BLE001 — construct raises many types
            logger.warning("packet_parse_failed", error=str(exc))
            return

        command_code = int(parsed.command_protocol)
        if command_code == int(IncomingCommand.BUTTON):
            self._emit_button_event(parsed.data)
        elif command_code == int(IncomingCommand.DEVICE_INFO):
            self._emit_device_info(parsed.data)
        else:
            logger.debug("unknown_incoming_command", code=f"{command_code:#06x}")

    def _emit_button_event(self, payload: object) -> None:
        # ``payload`` is the parsed ButtonPressedStruct container.
        event = ButtonEvent.create(
            index=int(payload.index),  # type: ignore[attr-defined]
            pressed=bool(payload.pressed),  # type: ignore[attr-defined]
            state=int(payload.state),  # type: ignore[attr-defined]
        )
        self._enqueue(event)
        logger.info(
            "button_event",
            index=event.index,
            pressed=event.pressed,
            state=f"{event.state:#04x}",
        )

    def _emit_device_info(self, payload: object) -> None:
        info_str = str(payload)
        event = DeviceInfoEvent.create(info=info_str)
        self._enqueue(event)
        logger.info("device_info", info=info_str)

    def _enqueue(self, event: ButtonEvent | DeviceInfoEvent) -> None:
        try:
            self._event_queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop the oldest event so the latest state always wins — better
            # than blocking the read loop and dropping live input.
            try:
                _ = self._event_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self._event_queue.put_nowait(event)
            logger.warning("event_queue_overflow_dropped_oldest")

    async def _require_transport(self) -> HidTransport:
        transport = self._transport
        if transport is not None:
            return transport
        await self._recover_transport(operation="transport_missing")
        transport = self._transport
        if transport is None:
            raise RuntimeError("transport unavailable while device is closing")
        return transport

    async def _recover_transport(
        self,
        *,
        operation: str,
        failed_transport: HidTransport | None = None,
        error: Exception | None = None,
    ) -> None:
        async with self._reconnect_lock:
            if self._closed:
                return

            current_transport = self._transport
            if (
                failed_transport is not None
                and current_transport is not None
                and current_transport is not failed_transport
            ):
                return

            if current_transport is not None:
                self._transport = None
                await current_transport.close()

            logger.warning(
                "transport_reconnect_started",
                operation=operation,
                error=str(error) if error is not None else None,
            )

            attempt = 0
            while not self._closed:
                attempt += 1
                reopened_transport: HidTransport | None = None
                try:
                    reopened_transport = self._transport_factory()
                    await self._restore_state(reopened_transport)
                except (DeviceNotFoundError, DeviceOpenError) as exc:
                    if reopened_transport is not None:
                        await reopened_transport.close()
                    logger.info(
                        "transport_reconnect_waiting",
                        operation=operation,
                        attempt=attempt,
                        error=str(exc),
                    )
                    await asyncio.sleep(self._reconnect_poll_interval_s)
                    continue
                except Exception as exc:  # noqa: BLE001
                    if reopened_transport is not None:
                        await reopened_transport.close()
                    logger.warning(
                        "transport_reconnect_retry_failed",
                        operation=operation,
                        attempt=attempt,
                        error=str(exc),
                    )
                    await asyncio.sleep(self._reconnect_poll_interval_s)
                    continue

                self._transport = reopened_transport
                logger.info(
                    "transport_reconnected",
                    operation=operation,
                    attempt=attempt,
                )
                return

    async def _restore_state(self, transport: HidTransport) -> None:
        if self._cached_brightness is not None:
            await self._send_raw(
                transport,
                OutgoingCommand.SET_BRIGHTNESS,
                str(self._cached_brightness).encode("ascii"),
            )

        if self._label_style_applied:
            await self._send_raw(
                transport,
                OutgoingCommand.SET_LABEL_STYLE,
                self._label_style_payload(),
            )

        buttons = self._buttons_for_restore()
        if buttons:
            command = (
                OutgoingCommand.SET_BUTTONS
                if self._button_state_is_full
                else OutgoingCommand.PARTIALLY_UPDATE_BUTTONS
            )
            await self._send_chunked_raw(
                transport,
                command,
                build_buttons_zip(buttons, fill_missing=self._button_state_is_full),
            )

        if self._last_small_window_data is not None:
            cpu, mem, gpu, time_str = self._last_small_window_data
            await self._send_raw(
                transport,
                OutgoingCommand.SET_SMALL_WINDOW_DATA,
                self._build_small_window_payload(
                    mode=self._cached_small_window_mode or SmallWindowMode.CLOCK,
                    cpu=cpu,
                    mem=mem,
                    gpu=gpu,
                    time_str=time_str,
                ),
            )

    def _remember_buttons(
        self, configs: tuple[ButtonConfig, ...], *, partial: bool
    ) -> None:
        if not partial:
            self._button_state = {int(cfg.index): cfg for cfg in configs}
            self._button_state_is_full = True
            return

        for cfg in configs:
            self._button_state[int(cfg.index)] = cfg

    def _buttons_for_restore(self) -> tuple[ButtonConfig, ...]:
        return tuple(
            cfg
            for _, cfg in sorted(
                self._button_state.items(),
                key=lambda item: item[0],
            )
        )

    async def _ensure_label_style(self) -> None:
        if self._label_style_applied:
            return
        await self._send(
            OutgoingCommand.SET_LABEL_STYLE,
            self._label_style_payload(),
        )
        self._label_style_applied = True
        logger.info("label_style_set", show_title=True, font_name="Roboto")

    @staticmethod
    def _label_style_payload() -> bytes:
        return json.dumps(
            DEFAULT_LABEL_STYLE,
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def _build_small_window_payload(
        *,
        mode: SmallWindowMode,
        cpu: int | None,
        mem: int | None,
        gpu: int | None,
        time_str: str | None,
    ) -> bytes:
        time_field = time_str or ""
        cpu_field = "" if cpu is None else str(cpu)
        mem_field = "" if mem is None else str(mem)
        gpu_field = "" if gpu is None else str(gpu)
        return (
            f"{int(mode)}|{cpu_field}|{mem_field}|{time_field}|{gpu_field}"
        ).encode("utf-8")

    async def _event_iterator(
        self,
    ) -> AsyncIterator[ButtonEvent | DeviceInfoEvent]:
        while not self._closed:
            event = await self._event_queue.get()
            yield event


# Re-exported so callers don't have to touch the construct layer directly.
__all__ = [
    "D200_SPEC",
    "ButtonPressedStruct",
    "UlanziD200Device",
]
