"""Tests for the daemon's small-window loop and loader integration."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest

from ulanzi_linux.application.config_loader import load_deck_config
from ulanzi_linux.application.daemon import DeckDaemon
from ulanzi_linux.application.deck_service import DeckService
from ulanzi_linux.domain.button_config import (
    ButtonConfig,
    DeckConfig,
    Page,
    SmallWindowConfig,
)
from ulanzi_linux.domain.commands import SmallWindowMode
from ulanzi_linux.domain.device import DeckDevice, DeckSpec
from ulanzi_linux.domain.events import ButtonEvent, DeviceInfoEvent
from ulanzi_linux.infrastructure.system_metrics import SystemMetricsReader
from ulanzi_linux.infrastructure.ulanzi_d200 import UlanziD200Device

# ---------------------------------------------------------------------- #
# Test doubles                                                           #
# ---------------------------------------------------------------------- #


class RecordingFakeDeck(DeckDevice):
    """DeckDevice double that records every outbound call we care about."""

    def __init__(self) -> None:
        self._spec = DeckSpec(
            name="FakeDeck",
            usb_vendor_id=0x1234,
            usb_product_id=0x5678,
            button_count=13,
            button_rows=3,
            button_cols=5,
            icon_width=196,
            icon_height=196,
        )
        self.button_uploads: list[tuple[ButtonConfig, ...]] = []
        self.small_window_data_calls: list[dict[str, object]] = []
        self.small_window_modes: list[SmallWindowMode] = []
        self.keep_alive_calls: int = 0
        self._queue: asyncio.Queue[ButtonEvent | DeviceInfoEvent] = asyncio.Queue()

    @property
    def spec(self) -> DeckSpec:
        return self._spec

    async def close(self) -> None:
        pass

    async def set_brightness(self, brightness: int, *, force: bool = False) -> None:
        pass

    async def keep_alive(self) -> None:
        self.keep_alive_calls += 1

    async def set_small_window_mode(self, mode: SmallWindowMode) -> None:
        self.small_window_modes.append(mode)

    async def set_small_window_data(
        self,
        *,
        cpu: int | None = 0,
        mem: int | None = 0,
        gpu: int | None = 0,
        time_str: str | None = None,
    ) -> None:
        self.small_window_data_calls.append(
            {"cpu": cpu, "mem": mem, "gpu": gpu, "time_str": time_str}
        )

    async def set_buttons(self, configs, *, partial: bool = False) -> None:  # type: ignore[override]
        self.button_uploads.append(tuple(configs))

    def events(self) -> AsyncIterator[ButtonEvent | DeviceInfoEvent]:
        async def _iter() -> AsyncIterator[ButtonEvent | DeviceInfoEvent]:
            while True:
                yield await self._queue.get()

        return _iter()


class FakeMetrics(SystemMetricsReader):
    """Deterministic metrics source with a call counter."""

    def __init__(
        self,
        *,
        cpu_values: list[int] | None = None,
        mem: int = 42,
        time_str: str = "14:32",
    ) -> None:
        self.cpu_values = cpu_values or [10, 25, 50]
        self.cpu_idx = 0
        self.mem = mem
        self.time_str_const = time_str
        self.cpu_reads = 0
        self.mem_reads = 0
        self.time_reads = 0
        self.last_format_fmt: str | None = None

    def read_cpu_percent(self) -> int:
        self.cpu_reads += 1
        val = self.cpu_values[min(self.cpu_idx, len(self.cpu_values) - 1)]
        self.cpu_idx += 1
        return val

    def read_memory_percent(self) -> int:
        self.mem_reads += 1
        return self.mem

    def format_time(self, fmt: str) -> str:
        self.time_reads += 1
        if fmt != "%S":
            self.last_format_fmt = fmt
        if fmt == "%S":
            if len(self.time_str_const) == 8:
                return self.time_str_const.split(":")[2]
            return "00"
        if fmt == "%H:%M:%S" and len(self.time_str_const) == 5:
            return f"{self.time_str_const}:00"
        return self.time_str_const


def _cfg_with_small_window(
    *,
    enabled: bool,
    interval_s: float = 0.05,
    show_metrics: bool = True,
    rotate_every_s: float | None = None,
) -> DeckConfig:
    return DeckConfig(
        pages={
            "main": Page(
                name="main",
                buttons=(ButtonConfig(index=0, label="A"),),
            )
        },
        default_page="main",
        small_window=SmallWindowConfig(
            enabled=enabled,
            interval_s=interval_s,
            time_format="%H:%M",
            show_metrics=show_metrics,
            rotate_every_s=rotate_every_s,
        ),
    )


# ---------------------------------------------------------------------- #
# Domain / config tests                                                  #
# ---------------------------------------------------------------------- #


def test_small_window_defaults_disabled() -> None:
    cfg = DeckConfig(
        pages={"default": Page(name="default")}, default_page="default"
    )
    assert cfg.small_window.enabled is False
    assert cfg.small_window.time_format == "%H:%M"
    assert cfg.small_window.rotate_every_s is None


def test_small_window_payload_uses_clock_wire_format() -> None:
    payload = UlanziD200Device._build_small_window_payload(
        mode=SmallWindowMode.CLOCK,
        cpu=17,
        mem=63,
        gpu=0,
        time_str="14:32:00",
    )
    assert payload == b"17,63,0,14:32:00"


def test_small_window_payload_supports_time_only_clock_updates() -> None:
    payload = UlanziD200Device._build_small_window_payload(
        mode=SmallWindowMode.CLOCK,
        cpu=0,
        mem=0,
        gpu=0,
        time_str="14:32:00",
    )
    assert payload == b"0,0,0,14:32:00"


@pytest.mark.asyncio
async def test_small_window_data_respects_cached_stats_mode_zero() -> None:
    from tests.test_reconnect import FakeTransport, _raw_small_window_payloads

    transport = FakeTransport()
    device = UlanziD200Device(transport)

    await device.set_small_window_mode(SmallWindowMode.STATS)
    await device.set_small_window_data(cpu=17, mem=63, gpu=0, time_str="14:32:00")
    await device.close()

    assert b"\x00" in _raw_small_window_payloads(transport.writes)
    assert b"17,63,0,14:32:00" in _raw_small_window_payloads(transport.writes)


def test_small_window_rejects_interval_below_floor() -> None:
    with pytest.raises(ValueError, match="interval_s"):
        SmallWindowConfig(enabled=True, interval_s=0.001)


def test_small_window_rejects_interval_above_watchdog() -> None:
    with pytest.raises(ValueError, match="interval_s"):
        SmallWindowConfig(enabled=True, interval_s=10.0)


def test_small_window_rejects_rotate_below_floor() -> None:
    with pytest.raises(ValueError, match="rotate_every_s"):
        SmallWindowConfig(enabled=True, rotate_every_s=0.001)


def test_loader_parses_small_window_block(tmp_path: Path) -> None:
    yaml_text = (
        "default_page: main\n"
        "small_window:\n"
        "  enabled: true\n"
        "  interval_s: 1.5\n"
        "  rotate_every_s: 5.0\n"
        "  time_format: \"%H:%M\"\n"
        "  background_color: \"#123456\"\n"
        "pages:\n"
        "  main:\n"
        "    buttons:\n"
        "      - index: 0\n"
        "        label: A\n"
    )
    path = tmp_path / "deck.yaml"
    path.write_text(yaml_text)
    cfg = load_deck_config(path)
    assert cfg.small_window.enabled is True
    assert cfg.small_window.interval_s == 1.5
    assert cfg.small_window.rotate_every_s == 5.0
    assert cfg.small_window.time_format == "%H:%M"
    assert cfg.small_window.background_color == "#123456"


def test_loader_small_window_block_on_legacy_schema(tmp_path: Path) -> None:
    yaml_text = """
small_window:
  enabled: true
buttons:
  - index: 0
    label: A
"""
    path = tmp_path / "deck.yaml"
    path.write_text(yaml_text)
    cfg = load_deck_config(path)
    assert cfg.small_window.enabled is True


# ---------------------------------------------------------------------- #
# Daemon loop tests                                                      #
# ---------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_small_window_loop_pushes_cpu_mem_time() -> None:
    fake = RecordingFakeDeck()
    metrics = FakeMetrics(cpu_values=[0, 42, 42, 42])  # 0 = priming result
    cfg = _cfg_with_small_window(enabled=True, interval_s=0.05)

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg, metrics_reader=metrics)
        stop = asyncio.Event()

        async def _stop_after_a_few_ticks() -> None:
            await asyncio.sleep(0.2)
            stop.set()

        await asyncio.gather(
            daemon.run(stop_event=stop),
            _stop_after_a_few_ticks(),
        )

    assert fake.button_uploads == []
    assert SmallWindowMode.STATS in fake.small_window_modes
    assert fake.small_window_data_calls, "expected live small-window payloads"
    last = fake.small_window_data_calls[-1]
    assert last["cpu"] == 42
    assert last["mem"] == 42
    assert last["gpu"] == 0
    assert last["time_str"] == "14:32:00"
    assert metrics.last_format_fmt == "%H:%M"
    # Heartbeat must NOT have run — small_window subsumes it.
    assert fake.keep_alive_calls == 0


@pytest.mark.asyncio
async def test_disabled_small_window_uses_heartbeat() -> None:
    fake = RecordingFakeDeck()
    metrics = FakeMetrics()
    cfg = _cfg_with_small_window(enabled=False)

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg, metrics_reader=metrics)
        # Shorten heartbeat so the test finishes fast.
        daemon._heartbeat_interval_s = 0.05  # type: ignore[attr-defined]
        stop = asyncio.Event()

        async def _stop_after() -> None:
            await asyncio.sleep(0.15)
            stop.set()

        await asyncio.gather(
            daemon.run(stop_event=stop),
            _stop_after(),
        )

    assert fake.keep_alive_calls >= 1
    assert SmallWindowMode.BACKGROUND in fake.small_window_modes
    assert fake.small_window_data_calls == []


@pytest.mark.asyncio
async def test_sync_layout_pushes_small_window_background_slot() -> None:
    fake = RecordingFakeDeck()
    cfg = DeckConfig(
        pages={
            "main": Page(
                name="main",
                buttons=(ButtonConfig(index=0, label="A"),),
            )
        },
        default_page="main",
        small_window=SmallWindowConfig(
            enabled=True,
            interval_s=0.05,
            background_color="#102030",
        ),
    )

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg)
        await daemon.sync_layout()

    assert len(fake.button_uploads) == 2
    assert [button.index for button in fake.button_uploads[0]] == [0]
    assert [button.index for button in fake.button_uploads[1]] == [13]
    assert fake.button_uploads[1][0].text_style.background_color == "#102030"


@pytest.mark.asyncio
async def test_small_window_can_run_in_time_only_mode() -> None:
    fake = RecordingFakeDeck()
    metrics = FakeMetrics(cpu_values=[0, 42, 42], mem=61, time_str="14:32")
    cfg = _cfg_with_small_window(enabled=True, interval_s=0.05, show_metrics=False)

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg, metrics_reader=metrics)
        stop = asyncio.Event()

        async def _stop_after() -> None:
            await asyncio.sleep(0.15)
            stop.set()

        await asyncio.gather(
            daemon.run(stop_event=stop),
            _stop_after(),
        )

    assert fake.button_uploads == []
    assert SmallWindowMode.CLOCK in fake.small_window_modes
    assert fake.small_window_data_calls
    last = fake.small_window_data_calls[-1]
    assert last["cpu"] == 0
    assert last["mem"] == 0
    assert last["gpu"] == 0
    assert last["time_str"] == "14:32:00"
    assert fake.keep_alive_calls == 0
    assert metrics.mem_reads == 0


@pytest.mark.asyncio
async def test_small_window_can_alternate_clock_and_stats() -> None:
    fake = RecordingFakeDeck()
    metrics = FakeMetrics(cpu_values=[0, 42, 42, 42], mem=61, time_str="14:32")
    cfg = _cfg_with_small_window(
        enabled=True,
        interval_s=0.05,
        show_metrics=True,
        rotate_every_s=0.1,
    )

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg, metrics_reader=metrics)
        stop = asyncio.Event()

        async def _stop_after() -> None:
            await asyncio.sleep(0.28)
            stop.set()

        await asyncio.gather(
            daemon.run(stop_event=stop),
            _stop_after(),
        )

    assert fake.button_uploads == []
    assert SmallWindowMode.CLOCK in fake.small_window_modes
    assert SmallWindowMode.STATS in fake.small_window_modes
    assert any(
        call["cpu"] == 0 and call["mem"] == 0 and call["time_str"] == "14:32:00"
        for call in fake.small_window_data_calls
    )
    assert any(
        call["cpu"] == 42 and call["mem"] == 61 and call["time_str"] == "14:32:00"
        for call in fake.small_window_data_calls
    )


@pytest.mark.asyncio
async def test_small_window_loop_survives_reader_exceptions() -> None:
    """A /proc hiccup must NOT bring down the watchdog ping."""
    fake = RecordingFakeDeck()

    class FlakyMetrics(FakeMetrics):
        def read_cpu_percent(self) -> int:  # type: ignore[override]
            self.cpu_reads += 1
            if self.cpu_reads == 2:
                raise OSError("simulated /proc failure")
            return super().read_cpu_percent()

    metrics = FlakyMetrics(cpu_values=[0, 11, 22, 33])
    cfg = _cfg_with_small_window(enabled=True, interval_s=0.05)

    async with DeckService.open_default(factory=lambda: cast(DeckDevice, fake)) as svc:
        daemon = DeckDaemon(svc, cfg, metrics_reader=metrics)
        stop = asyncio.Event()

        async def _stop_after() -> None:
            await asyncio.sleep(0.3)
            stop.set()

        await asyncio.gather(
            daemon.run(stop_event=stop),
            _stop_after(),
        )

    # Enough ticks ran that we recovered at least one successful push after
    # the injected failure.
    assert any(call["cpu"] == 33 for call in fake.small_window_data_calls)
