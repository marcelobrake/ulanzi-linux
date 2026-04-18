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

from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

import structlog

logger = structlog.get_logger(__name__)


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


class ProcSystemMetrics:
    """``/proc``-backed ``SystemMetricsReader`` for Linux hosts."""

    # Exposed as attributes for testing — tests can swap to tmp paths.
    proc_stat: Path = Path("/proc/stat")
    proc_meminfo: Path = Path("/proc/meminfo")

    def __init__(
        self,
        *,
        proc_stat: Path | None = None,
        proc_meminfo: Path | None = None,
    ) -> None:
        if proc_stat is not None:
            self.proc_stat = proc_stat
        if proc_meminfo is not None:
            self.proc_meminfo = proc_meminfo
        self._last_cpu_sample: tuple[int, int] | None = None

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


def _clamp_percent(value: float) -> int:
    """Clamp a float percentage into an int in ``[0, 100]``."""
    return max(0, min(100, int(round(value))))


__all__ = ["ProcSystemMetrics", "SystemMetricsReader"]
