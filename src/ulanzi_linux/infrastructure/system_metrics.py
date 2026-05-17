"""System metrics reader for the D200 small-window overlay.

Exposes a ``SystemMetricsReader`` Protocol and a Linux-native concrete
implementation (``ProcSystemMetrics``) that reads ``/proc`` directly —
no external dependencies (psutil) so the daemon can ship lean and
reproducibly on any glibc distro.

GPU stats are intentionally out of scope: vendor telemetry (nvidia-smi,
radeontop, intel_gpu_top) is a per-vendor matrix that slows progress and
adds runtime deps. The reader hard-codes ``gpu=0`` — the field is sent
on the wire but the firmware ignores absent values gracefully.

The reader is stateful for CPU: a single sample of ``/proc/stat`` is
useless (absolute jiffy counts since boot) — the returned percentage is
a delta between the previous and current sample. First call therefore
returns 0 intentionally, so callers should prime the reader before
starting a display loop if they care about the first tick.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

import structlog

logger = structlog.get_logger(__name__)

SMALL_WINDOW_METRIC_LABELS: dict[str, str] = {
    "cpu": "CPU",
    "memory": "MEM",
    "gpu": "GPU",
    "temperature": "TEMP",
    "disk": "DISK",
    "network": "NET",
    "battery": "BAT",
}


@runtime_checkable
class SystemMetricsReader(Protocol):
    """Minimal surface the daemon needs from a metrics source."""

    def read_cpu_percent(self) -> int:
        """Return 0-100 integer CPU utilisation since the last call."""
        ...

    def read_memory_percent(self) -> int:
        """Return 0-100 integer memory utilisation (MemTotal - MemAvailable)."""
        ...

    def format_time(self, fmt: str) -> str:
        """Return the current local date/time formatted with ``fmt``."""
        ...

    def read_metric_value(self, metric: str) -> str:
        """Return a human-readable metric value for the small window."""
        ...


class ProcSystemMetrics:
    """``/proc``-backed ``SystemMetricsReader`` for Linux hosts."""

    # Exposed as attributes for testing — tests can swap to tmp paths.
    proc_stat: Path = Path("/proc/stat")
    proc_meminfo: Path = Path("/proc/meminfo")
    proc_net_dev: Path = Path("/proc/net/dev")
    sys_thermal: Path = Path("/sys/class/thermal")
    sys_power_supply: Path = Path("/sys/class/power_supply")
    sys_drm: Path = Path("/sys/class/drm")

    def __init__(
        self,
        *,
        proc_stat: Path | None = None,
        proc_meminfo: Path | None = None,
        proc_net_dev: Path | None = None,
        sys_thermal: Path | None = None,
        sys_power_supply: Path | None = None,
        sys_drm: Path | None = None,
    ) -> None:
        if proc_stat is not None:
            self.proc_stat = proc_stat
        if proc_meminfo is not None:
            self.proc_meminfo = proc_meminfo
        if proc_net_dev is not None:
            self.proc_net_dev = proc_net_dev
        if sys_thermal is not None:
            self.sys_thermal = sys_thermal
        if sys_power_supply is not None:
            self.sys_power_supply = sys_power_supply
        if sys_drm is not None:
            self.sys_drm = sys_drm
        self._last_cpu_sample: tuple[int, int] | None = None
        self._last_network_sample: tuple[int, float] | None = None

    # ------------------------------------------------------------------ #
    # CPU                                                                #
    # ------------------------------------------------------------------ #

    def read_cpu_percent(self) -> int:
        current = self._read_cpu_sample()
        if current is None:
            return 0
        previous = self._last_cpu_sample
        self._last_cpu_sample = current
        if previous is None:
            return 0  # no baseline yet
        total_delta = current[0] - previous[0]
        idle_delta = current[1] - previous[1]
        if total_delta <= 0:
            # Clock went backwards (suspend/resume) or counters wrapped;
            # discard and wait for the next sample to re-baseline.
            return 0
        busy = (total_delta - idle_delta) / total_delta * 100.0
        return _clamp_percent(busy)

    def _read_cpu_sample(self) -> tuple[int, int] | None:
        """Parse the aggregate ``cpu`` line from ``/proc/stat``.

        Returns ``(total_jiffies, idle_jiffies)`` or ``None`` on error.
        """
        try:
            first_line = self.proc_stat.read_text().splitlines()[0]
        except (OSError, IndexError) as exc:
            logger.warning("proc_stat_read_failed", error=str(exc))
            return None
        fields = first_line.split()
        # Expected: "cpu  user nice system idle iowait irq softirq steal ..."
        if len(fields) < 5 or fields[0] != "cpu":
            logger.warning("proc_stat_unexpected_shape", line=first_line)
            return None
        try:
            values = [int(x) for x in fields[1:]]
        except ValueError as exc:
            logger.warning("proc_stat_parse_failed", error=str(exc))
            return None
        idle = values[3]
        iowait = values[4] if len(values) > 4 else 0
        idle_all = idle + iowait
        total = sum(values)
        return total, idle_all

    # ------------------------------------------------------------------ #
    # Memory                                                             #
    # ------------------------------------------------------------------ #

    def read_memory_percent(self) -> int:
        mem_total = 0
        mem_available = 0
        try:
            for line in self.proc_meminfo.read_text().splitlines():
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_available = int(line.split()[1])
                if mem_total and mem_available:
                    break
        except (OSError, ValueError, IndexError) as exc:
            logger.warning("proc_meminfo_read_failed", error=str(exc))
            return 0
        if mem_total <= 0:
            return 0
        used = (mem_total - mem_available) / mem_total * 100.0
        return _clamp_percent(used)

    # ------------------------------------------------------------------ #
    # Time                                                               #
    # ------------------------------------------------------------------ #

    def format_time(self, fmt: str) -> str:
        return datetime.now().strftime(fmt)

    def read_metric_value(self, metric: str) -> str:
        if metric == "cpu":
            return f"{self.read_cpu_percent()}%"
        if metric == "memory":
            return f"{self.read_memory_percent()}%"
        if metric == "gpu":
            gpu = self.read_gpu_percent()
            return "n/a" if gpu is None else f"{gpu}%"
        if metric == "temperature":
            temp = self.read_temperature_celsius()
            return "n/a" if temp is None else f"{temp}C"
        if metric == "disk":
            return f"{self.read_disk_percent()}%"
        if metric == "network":
            return self.read_network_rate()
        if metric == "battery":
            battery = self.read_battery_percent()
            return "n/a" if battery is None else f"{battery}%"
        raise ValueError(f"unsupported metric: {metric}")

    def read_temperature_celsius(self) -> int | None:
        candidates = sorted(self.sys_thermal.glob("thermal_zone*/temp"))
        for candidate in candidates:
            try:
                raw = candidate.read_text(encoding="utf-8").strip()
                value = int(raw)
            except (OSError, ValueError):
                continue
            if 1_000 <= value <= 200_000:
                return max(0, round(value / 1000.0))
            if 1 <= value <= 200:
                return value
        return None

    def read_disk_percent(self, path: Path = Path("/")) -> int:
        try:
            stats = os.statvfs(path)
        except OSError as exc:
            logger.warning("disk_usage_read_failed", error=str(exc), path=str(path))
            return 0
        total = stats.f_blocks * stats.f_frsize
        free = stats.f_bavail * stats.f_frsize
        if total <= 0:
            return 0
        used = (total - free) / total * 100.0
        return _clamp_percent(used)

    def read_network_rate(self) -> str:
        current = self._read_network_total_bytes()
        if current is None:
            return "n/a"
        now = time.monotonic()
        previous = self._last_network_sample
        self._last_network_sample = (current, now)
        if previous is None:
            return "0 B/s"
        delta_bytes = max(0, current - previous[0])
        delta_time = max(0.001, now - previous[1])
        rate = delta_bytes / delta_time
        return f"{_format_bytes(rate)}/s"

    def _read_network_total_bytes(self) -> int | None:
        try:
            lines = self.proc_net_dev.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("proc_net_dev_read_failed", error=str(exc))
            return None
        total = 0
        for line in lines[2:]:
            if ":" not in line:
                continue
            iface, payload = line.split(":", 1)
            iface = iface.strip()
            if iface == "lo":
                continue
            fields = payload.split()
            if len(fields) < 16:
                continue
            try:
                recv = int(fields[0])
                sent = int(fields[8])
            except ValueError:
                continue
            total += recv + sent
        return total

    def read_battery_percent(self) -> int | None:
        for candidate in sorted(self.sys_power_supply.glob("BAT*/capacity")):
            try:
                return _clamp_percent(float(candidate.read_text(encoding="utf-8").strip()))
            except (OSError, ValueError):
                continue
        return None

    def read_gpu_percent(self) -> int | None:
        for candidate in sorted(self.sys_drm.glob("card*/device/gpu_busy_percent")):
            try:
                return _clamp_percent(float(candidate.read_text(encoding="utf-8").strip()))
            except (OSError, ValueError):
                continue
        for candidate in sorted(self.sys_drm.glob("card*/device/load")):
            try:
                raw = float(candidate.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                continue
            value = raw / 10.0 if raw > 100 else raw
            return _clamp_percent(value)
        return None


def _clamp_percent(value: float) -> int:
    """Clamp a float percentage into an int in ``[0, 100]``."""
    return max(0, min(100, round(value)))


def _format_bytes(value: float) -> str:
    units = ("B", "K", "M", "G")
    amount = float(value)
    for unit in units:
        if amount < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{round(amount)} {unit}"
            return f"{amount:.1f} {unit}".replace(".0 ", " ")
        amount /= 1024.0


__all__ = ["SMALL_WINDOW_METRIC_LABELS", "ProcSystemMetrics", "SystemMetricsReader"]
