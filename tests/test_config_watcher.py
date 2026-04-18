"""Tests for ConfigWatcher — filesystem polling + callback dispatch."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ulanzi_linux.application.config_watcher import ConfigWatcher


async def _run_until_triggers(
    watcher: ConfigWatcher,
    triggered: asyncio.Event,
    *,
    timeout_s: float,
) -> None:
    """Drive the watcher until ``triggered`` fires or a timeout elapses."""
    stop = asyncio.Event()

    async def _wait_and_stop() -> None:
        try:
            await asyncio.wait_for(triggered.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            pass
        stop.set()

    await asyncio.gather(watcher.run(stop), _wait_and_stop())


@pytest.mark.asyncio
async def test_watcher_fires_callback_on_mtime_change(tmp_path: Path) -> None:
    path = tmp_path / "deck.yaml"
    path.write_text("version: 1\n")

    calls: list[Path] = []
    triggered = asyncio.Event()

    async def _on_change(p: Path) -> None:
        calls.append(p)
        triggered.set()

    watcher = ConfigWatcher(path, _on_change, poll_interval_s=0.05)

    async def _edit_after_warmup() -> None:
        await asyncio.sleep(0.15)
        # Touching mtime + growing size guarantees the signature changes,
        # even on filesystems with coarse mtime resolution.
        path.write_text("version: 2\n# edited\n")

    editor = asyncio.create_task(_edit_after_warmup())
    try:
        await _run_until_triggers(watcher, triggered, timeout_s=2.0)
    finally:
        editor.cancel()
        try:
            await editor
        except asyncio.CancelledError:
            pass

    assert calls == [path.resolve()]


@pytest.mark.asyncio
async def test_watcher_swallows_callback_exceptions(tmp_path: Path) -> None:
    path = tmp_path / "deck.yaml"
    path.write_text("a\n")

    calls: list[int] = []
    triggered_second = asyncio.Event()

    async def _on_change(_: Path) -> None:
        calls.append(len(calls))
        if len(calls) == 1:
            raise RuntimeError("boom")
        triggered_second.set()

    watcher = ConfigWatcher(path, _on_change, poll_interval_s=0.05)

    async def _edits() -> None:
        await asyncio.sleep(0.15)
        path.write_text("b\n")  # first change -> raises
        await asyncio.sleep(0.25)
        path.write_text("c\ncontent\n")  # second change -> must still fire

    editor = asyncio.create_task(_edits())
    try:
        await _run_until_triggers(watcher, triggered_second, timeout_s=2.0)
    finally:
        editor.cancel()
        try:
            await editor
        except asyncio.CancelledError:
            pass

    # Both edits were observed even though the first callback raised.
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_watcher_tolerates_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "deck.yaml"
    path.write_text("a\n")

    calls: list[Path] = []
    triggered = asyncio.Event()

    async def _on_change(p: Path) -> None:
        calls.append(p)
        triggered.set()

    watcher = ConfigWatcher(path, _on_change, poll_interval_s=0.05)

    async def _vanish_then_restore() -> None:
        await asyncio.sleep(0.15)
        path.unlink()
        await asyncio.sleep(0.2)
        path.write_text("restored\n")

    editor = asyncio.create_task(_vanish_then_restore())
    try:
        await _run_until_triggers(watcher, triggered, timeout_s=2.0)
    finally:
        editor.cancel()
        try:
            await editor
        except asyncio.CancelledError:
            pass

    # After the file reappears the callback fires exactly once — no
    # spurious triggers while the file was missing.
    assert len(calls) == 1
