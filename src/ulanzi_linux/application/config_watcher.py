"""Filesystem watcher for a single YAML config file.

Polls ``(mtime, size)`` on a fixed interval and invokes an async callback
whenever either changes. We intentionally avoid ``inotify``/``fsevents``
bindings:

* Adds a native dependency per-platform.
* Behaves poorly on non-local mounts (sshfs, overlayfs, Docker bind
  mounts) — exactly the surfaces operators tend to edit configs from.
* Coalescing events from those APIs is non-trivial; polling gives
  naturally debounced behaviour.

A 1-second tick is more than fast enough for a human-edited config and
light on the kernel — one ``stat(2)`` per second is nothing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Reloads are driven by human saves; sub-second polling is pointless.
DEFAULT_POLL_INTERVAL_S: float = 1.0

# Callback receives the path that changed. It is async so the daemon can
# perform IO (re-parse YAML, re-upload layout) without blocking the tick.
ReloadCallback = Callable[[Path], Awaitable[None]]


class ConfigWatcher:
    """Watches a file and fires ``on_change`` when mtime/size shifts.

    The watcher is intentionally *not* responsible for parsing the file —
    it only detects "something moved". The callback decides how to react
    (reload, ignore, whatever). This keeps filesystem concerns and
    domain-config concerns separated.
    """

    def __init__(
        self,
        path: str | Path,
        on_change: ReloadCallback,
        *,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    ) -> None:
        self._path = Path(path).expanduser().resolve()
        self._on_change = on_change
        self._poll_interval_s = poll_interval_s
        self._last_signature: tuple[float, int] | None = None

    @property
    def path(self) -> Path:
        return self._path

    async def run(self, stop_event: asyncio.Event) -> None:
        """Poll until ``stop_event`` is set.

        Swallows callback exceptions so a single bad reload never kills
        the watcher — the daemon needs this loop to stay up.
        """
        self._last_signature = self._read_signature()
        logger.info(
            "config_watch_started",
            path=str(self._path),
            interval_s=self._poll_interval_s,
        )
        try:
            while not stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=self._poll_interval_s
                    )
                except asyncio.TimeoutError:
                    pass  # normal tick
                if stop_event.is_set():
                    break
                await self._tick()
        finally:
            logger.info("config_watch_stopped", path=str(self._path))

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _read_signature(self) -> tuple[float, int] | None:
        """Return (mtime, size) or ``None`` if the file is gone.

        A missing file is a valid transient state — editors often write
        to a temp file and ``rename(2)`` over the target; during that
        window ``stat`` can fail. We treat it as 'no change since last
        check' instead of thrashing on reloads.
        """
        try:
            st = self._path.stat()
        except FileNotFoundError:
            return None
        return (st.st_mtime, st.st_size)

    async def _tick(self) -> None:
        current = self._read_signature()
        if current is None:
            # File vanished — log once per disappearance, not every tick.
            if self._last_signature is not None:
                logger.warning("config_file_missing", path=str(self._path))
                self._last_signature = None
            return
        if current == self._last_signature:
            return
        logger.info(
            "config_change_detected",
            path=str(self._path),
            previous=self._last_signature,
            current=current,
        )
        self._last_signature = current
        try:
            await self._on_change(self._path)
        except Exception as exc:  # noqa: BLE001
            # Callback is expected to handle its own errors (e.g. parse
            # failures), but we defend in depth — losing the watcher
            # because the daemon raised is strictly worse than a noisy
            # log line.
            logger.error(
                "config_reload_callback_failed",
                path=str(self._path),
                error=str(exc),
            )


__all__ = ["ConfigWatcher", "DEFAULT_POLL_INTERVAL_S", "ReloadCallback"]
