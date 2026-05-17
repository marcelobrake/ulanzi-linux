"""Tests for ProcSystemMetrics — /proc parsing and delta math."""

from __future__ import annotations

from pathlib import Path

from ulanzi_linux.infrastructure.system_metrics import ProcSystemMetrics


def _stat_line(user: int, nice: int, sys_: int, idle: int, iowait: int = 0) -> str:
    # /proc/stat aggregate "cpu" row — subsequent fields allowed but ignored.
    return f"cpu  {user} {nice} {sys_} {idle} {iowait} 0 0 0 0 0\n"


def test_cpu_percent_first_call_is_zero(tmp_path: Path) -> None:
    stat_path = tmp_path / "stat"
    stat_path.write_text(_stat_line(100, 0, 50, 800))
    reader = ProcSystemMetrics(proc_stat=stat_path, proc_meminfo=Path("/dev/null"))
    # No baseline yet — a single sample cannot produce a useful delta.
    assert reader.read_cpu_percent() == 0


def test_cpu_percent_delta_between_samples(tmp_path: Path) -> None:
    stat_path = tmp_path / "stat"
    meminfo_path = tmp_path / "meminfo"
    meminfo_path.write_text("MemTotal: 1 kB\nMemAvailable: 1 kB\n")

    # Sample 1: total=1000 jiffies, idle_all=idle+iowait=850
    stat_path.write_text(_stat_line(100, 0, 50, 800, iowait=50))
    reader = ProcSystemMetrics(proc_stat=stat_path, proc_meminfo=meminfo_path)
    assert reader.read_cpu_percent() == 0  # prime

    # Sample 2: total=1300, idle_all=900
    # delta_total=300, delta_idle=50 -> busy = (300-50)/300 = 83.3% -> 83
    stat_path.write_text(_stat_line(200, 0, 200, 800, iowait=100))
    assert reader.read_cpu_percent() == 83


def test_cpu_percent_tolerates_negative_delta(tmp_path: Path) -> None:
    """Counters moving backwards (suspend/resume) must not crash or lie."""
    stat_path = tmp_path / "stat"
    stat_path.write_text(_stat_line(500, 0, 500, 500))
    reader = ProcSystemMetrics(proc_stat=stat_path, proc_meminfo=Path("/dev/null"))
    reader.read_cpu_percent()  # prime

    stat_path.write_text(_stat_line(100, 0, 100, 100))  # wound back
    assert reader.read_cpu_percent() == 0


def test_memory_percent_computes_used_fraction(tmp_path: Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal:       16000000 kB\n"
        "MemFree:         2000000 kB\n"
        "MemAvailable:    4000000 kB\n"
        "Buffers:          100000 kB\n"
    )
    reader = ProcSystemMetrics(proc_stat=Path("/dev/null"), proc_meminfo=meminfo)
    # (16M - 4M) / 16M = 75%
    assert reader.read_memory_percent() == 75


def test_memory_percent_returns_zero_when_unreadable(tmp_path: Path) -> None:
    reader = ProcSystemMetrics(
        proc_stat=Path("/dev/null"),
        proc_meminfo=tmp_path / "missing",
    )
    assert reader.read_memory_percent() == 0


def test_format_time_uses_strftime_pattern() -> None:
    reader = ProcSystemMetrics(
        proc_stat=Path("/dev/null"), proc_meminfo=Path("/dev/null")
    )
    out = reader.format_time("%Y")
    assert out.isdigit() and len(out) == 4  # year


def test_metric_value_formats_human_readable_strings(tmp_path: Path) -> None:
    stat_path = tmp_path / "stat"
    stat_path.write_text(_stat_line(100, 0, 50, 800))
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: 100 kB\nMemAvailable: 50 kB\n")
    netdev = tmp_path / "netdev"
    netdev.write_text(
        "Inter-|   Receive                                                |  Transmit\n"
        " face |bytes    packets errs drop fifo frame compressed multicast|"
        "bytes    packets errs drop fifo colls carrier compressed\n"
        "  eth0: 100 0 0 0 0 0 0 0 200 0 0 0 0 0 0 0\n"
    )
    thermal = tmp_path / "thermal"
    (thermal / "thermal_zone0").mkdir(parents=True)
    (thermal / "thermal_zone0" / "temp").write_text("55000")
    power = tmp_path / "power"
    (power / "BAT0").mkdir(parents=True)
    (power / "BAT0" / "capacity").write_text("82")
    drm = tmp_path / "drm"
    (drm / "card0" / "device").mkdir(parents=True)
    (drm / "card0" / "device" / "gpu_busy_percent").write_text("41")

    reader = ProcSystemMetrics(
        proc_stat=stat_path,
        proc_meminfo=meminfo,
        proc_net_dev=netdev,
        sys_thermal=thermal,
        sys_power_supply=power,
        sys_drm=drm,
    )

    assert reader.read_metric_value("cpu") == "0%"
    assert reader.read_metric_value("memory") == "50%"
    assert reader.read_metric_value("temperature") == "55C"
    assert reader.read_metric_value("disk").endswith("%")
    assert reader.read_metric_value("battery") == "82%"
    assert reader.read_metric_value("gpu") == "41%"
    assert reader.read_metric_value("network").endswith("/s")
