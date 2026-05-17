"""Daemon that binds deck button events to host-side actions.

Runs up to four concurrent concerns:
    * ``_heartbeat_loop``   — periodic watchdog ping so firmware stays in
                              host-driven mode and doesn't fall back to the
                              standalone 'Ulanzi Studio' screen.
    * ``_event_loop``       — consumes button events and dispatches actions,
                              intercepting ``SwitchPageAction`` before it
                              reaches the runner (paging is a daemon concern,
                              not a host action).
    * optional config watch — polls the YAML file and triggers
                              ``reload_config`` on change, keeping the
                              running deck in sync with disk edits without
                              restart.
    * ``stop_event`` watch  — graceful shutdown on SIGINT/SIGTERM.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from pathlib import Path

import structlog

from ulanzi_linux.application.action_runner import ActionRunner
from ulanzi_linux.application.config_loader import load_deck_config
from ulanzi_linux.application.config_watcher import ConfigWatcher
from ulanzi_linux.application.deck_service import DeckService
from ulanzi_linux.domain.button_config import (
    ButtonConfig,
    DeckConfig,
    PredefinedCommandAction,
    ShellAction,
    ShortcutAction,
    SwitchPageAction,
    TextStyle,
    UrlAction,
)
from ulanzi_linux.domain.commands import SmallWindowMode
from ulanzi_linux.domain.events import ButtonEvent
from ulanzi_linux.infrastructure.system_metrics import (
    SMALL_WINDOW_METRIC_LABELS,
    ProcSystemMetrics,
    SystemMetricsReader,
)

logger = structlog.get_logger(__name__)

INFO_WINDOW_INDEX = 13

# Firmware watchdog fires around the 5s mark; we ping well below that to
# tolerate scheduling jitter and USB latency.
DEFAULT_HEARTBEAT_INTERVAL_S: float = 2.0


def _looks_like_hhmm(value: str) -> bool:
    return len(value) == 5 and value[2] == ":" and value[:2].isdigit() and value[3:].isdigit()


def _action_log_fields(action: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "action_type": getattr(action, "type", type(action).__name__),
    }
    if isinstance(action, ShellAction):
        fields["cmd"] = action.cmd
    elif isinstance(action, ShortcutAction):
        fields["keys"] = action.keys
    elif isinstance(action, UrlAction):
        fields["url"] = action.url
    elif isinstance(action, PredefinedCommandAction):
        fields["command_id"] = action.command_id
    elif isinstance(action, SwitchPageAction):
        fields["target_page"] = action.page
    return fields


def _rotates_small_window(sw_cfg: object) -> bool:
    return bool(
        getattr(sw_cfg, "show_metrics", False)
        and getattr(sw_cfg, "rotate_every_s", None) is not None
    )


def _uses_custom_small_window(sw_cfg: object) -> bool:
    return bool(getattr(sw_cfg, "metrics_items", ()))


def _small_window_clock_button(*, background_color: str, time_str: str) -> ButtonConfig:
    return ButtonConfig(
        index=INFO_WINDOW_INDEX,
        label=time_str,
        text_style=TextStyle(
            background_color=background_color,
            text_color="#F8FAFC",
            font_family="DejaVu Sans Mono",
            font_size=48,
            bold=True,
        ),
    )


def _small_window_metrics_button(
    *,
    background_color: str,
    metric_lines: list[str],
) -> ButtonConfig:
    font_size = 44 if len(metric_lines) == 1 else 34 if len(metric_lines) == 2 else 28
    return ButtonConfig(
        index=INFO_WINDOW_INDEX,
        label="\n".join(metric_lines),
        text_style=TextStyle(
            background_color=background_color,
            text_color="#F8FAFC",
            font_family="DejaVu Sans Mono",
            font_size=font_size,
            bold=True,
        ),
    )


class DeckDaemon:
    """Glue: pushes layout, heartbeats the firmware, runs actions on press.

    Holds the currently active page name as mutable state; ``switch_to``
    and ``reload_config`` are the only supported mutations so callers
    cannot desync the displayed layout from the in-memory page.
    """

    def __init__(
        self,
        service: DeckService,
        config: DeckConfig,
        runner: ActionRunner | None = None,
        *,
        heartbeat_interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
        metrics_reader: SystemMetricsReader | None = None,
    ) -> None:
        self._service = service
        self._config = config
        self._runner = runner or ActionRunner()
        self._heartbeat_interval_s = heartbeat_interval_s
        # Lazily default to /proc-backed metrics so tests can inject fakes.
        self._metrics_reader: SystemMetricsReader = (
            metrics_reader or ProcSystemMetrics()
        )
        self._current_page: str = config.default_page
        # Guards reload_config / switch_to against racing the event loop
        # uploading a stale layout mid-swap.
        self._state_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    @property
    def current_page(self) -> str:
        return self._current_page

    @property
    def config(self) -> DeckConfig:
        return self._config

    async def sync_layout(self) -> None:
        """Push the current page's icons/labels to the device."""
        async with self._state_lock:
            await self._push_page(self._current_page)

    async def switch_to(self, page_name: str) -> None:
        """Switch active page and upload its layout.

        Silently no-ops when the requested page is already active to avoid
        redundant USB traffic.
        """
        async with self._state_lock:
            if page_name == self._current_page:
                logger.info("switch_page_noop", page=page_name)
                return
            if page_name not in self._config.pages:
                logger.warning(
                    "switch_page_unknown",
                    requested=page_name,
                    known=list(self._config.pages.keys()),
                )
                return
            self._current_page = page_name
            await self._push_page(page_name)
            logger.info("page_switched", page=page_name)

    async def reload_config(self, path: str | Path) -> None:
        """Atomically swap the running config for the one on disk.

        Parse + validation happens *before* touching daemon state — a
        broken YAML leaves the previous config running and surfaces the
        error in logs rather than bricking the deck mid-edit.

        The current page is preserved across reload when it still exists
        in the new config; otherwise we fall back to the new default.
        """
        try:
            new_config = load_deck_config(path)
        except Exception as exc:
            logger.error(
                "config_reload_parse_failed",
                path=str(path),
                error=str(exc),
            )
            return

        async with self._state_lock:
            previous_page = self._current_page
            if previous_page in new_config.pages:
                next_page = previous_page
            else:
                next_page = new_config.default_page
                logger.info(
                    "config_reload_page_changed",
                    previous=previous_page,
                    next=next_page,
                    reason="page_not_in_new_config",
                )
            self._config = new_config
            self._current_page = next_page
            await self._push_page(next_page)
            logger.info(
                "config_reloaded",
                path=str(path),
                pages=list(new_config.pages.keys()),
                active_page=next_page,
                fixed_buttons=len(new_config.fixed_buttons),
            )

    async def run(
        self,
        *,
        stop_event: asyncio.Event | None = None,
        watcher: ConfigWatcher | None = None,
    ) -> None:
        """Run heartbeat, event loop and (optional) config watcher.

        The event loop blocks inside the service's async iterator, so a
        cooperative ``stop_event.is_set()`` poll is not sufficient — we
        cancel the task when the stop signal fires and swallow the
        resulting ``CancelledError``.
        """
        stop = stop_event or asyncio.Event()
        sw_cfg = self._config.small_window
        logger.info(
            "daemon_started",
            pages=list(self._config.pages.keys()),
            default_page=self._current_page,
            fixed_buttons=len(self._config.fixed_buttons),
            watch=watcher is not None,
            small_window=sw_cfg.enabled,
        )
        tasks: list[asyncio.Task[None]] = [
            asyncio.create_task(
                self._event_loop(stop), name="ulanzi_daemon_events"
            ),
            asyncio.create_task(
                self._status_loop(stop), name="ulanzi_daemon_status"
            ),
        ]
        if watcher is not None:
            tasks.append(
                asyncio.create_task(
                    watcher.run(stop), name="ulanzi_daemon_config_watch"
                )
            )
        try:
            await stop.wait()
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            for task in tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    logger.error(
                        "daemon_task_error",
                        task=task.get_name(),
                        error=str(exc),
                    )
            logger.info("daemon_stopped")

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    async def _push_page(self, page_name: str) -> None:
        buttons = self._config.buttons_for(page_name)
        visible_buttons = tuple(
            button
            for button in buttons
            if button.index < self._service.spec.button_count
        )
        await self._service._device.set_buttons(visible_buttons)
        await self._service._device.set_buttons(
            (
                ButtonConfig(
                    index=INFO_WINDOW_INDEX,
                    text_style=TextStyle(
                        background_color=self._config.small_window.background_color,
                    ),
                ),
            ),
            partial=True,
        )
        logger.info(
            "layout_synced",
            page=page_name,
            buttons=len(visible_buttons),
            action_only_buttons=len(buttons) - len(visible_buttons),
            small_window_background_color=self._config.small_window.background_color,
        )

    def _wire_time_string(self, configured_format: str) -> str:
        rendered = self._metrics_reader.format_time(configured_format)
        if _looks_like_hhmm(rendered):
            return f"{rendered}:{self._metrics_reader.format_time('%S')}"
        if rendered:
            return rendered
        return self._metrics_reader.format_time("%H:%M:%S")

    def _custom_metric_lines(self, metrics_items: tuple[str, ...]) -> list[str]:
        lines: list[str] = []
        for metric in metrics_items:
            label = SMALL_WINDOW_METRIC_LABELS.get(metric, metric.upper())
            value = self._metrics_reader.read_metric_value(metric)
            lines.append(f"{label:<4} {value}")
        return lines

    async def _status_loop(self, stop_event: asyncio.Event) -> None:
        logger.info("status_loop_started")
        active_mode: SmallWindowMode | None = None
        device_mode: SmallWindowMode | None = None
        mode_started_at: float | None = None
        metrics_primed = False
        strategy_key: tuple[bool, bool, float | None, tuple[str, ...]] | None = None
        try:
            while not stop_event.is_set():
                try:
                    sw_cfg = self._config.small_window
                    current_strategy = (
                        sw_cfg.enabled,
                        sw_cfg.show_metrics,
                        sw_cfg.rotate_every_s,
                        tuple(sw_cfg.metrics_items),
                    )
                    if strategy_key != current_strategy:
                        active_mode = None
                        device_mode = None
                        mode_started_at = None
                        metrics_primed = False
                        strategy_key = current_strategy
                    if sw_cfg.enabled:
                        now = time.monotonic()
                        next_mode_switch_in: float | None = None
                        if sw_cfg.show_metrics:
                            if _rotates_small_window(sw_cfg):
                                if (
                                    active_mode not in {
                                        SmallWindowMode.CLOCK,
                                        SmallWindowMode.STATS,
                                    }
                                    or mode_started_at is None
                                ):
                                    desired_mode = SmallWindowMode.CLOCK
                                    next_mode_switch_in = sw_cfg.rotate_every_s
                                else:
                                    elapsed = now - mode_started_at
                                    if elapsed >= sw_cfg.rotate_every_s:
                                        desired_mode = (
                                            SmallWindowMode.STATS
                                            if active_mode == SmallWindowMode.CLOCK
                                            else SmallWindowMode.CLOCK
                                        )
                                        next_mode_switch_in = sw_cfg.rotate_every_s
                                    else:
                                        desired_mode = active_mode
                                        next_mode_switch_in = (
                                            sw_cfg.rotate_every_s - elapsed
                                        )
                            else:
                                desired_mode = SmallWindowMode.STATS
                        else:
                            desired_mode = SmallWindowMode.CLOCK
                        if _uses_custom_small_window(sw_cfg):
                            if device_mode != SmallWindowMode.BACKGROUND:
                                await self._service._device.set_small_window_mode(
                                    SmallWindowMode.BACKGROUND
                                )
                                device_mode = SmallWindowMode.BACKGROUND
                            if active_mode != desired_mode:
                                active_mode = desired_mode
                                mode_started_at = now
                                metrics_primed = False
                                if _rotates_small_window(sw_cfg):
                                    next_mode_switch_in = sw_cfg.rotate_every_s
                            if sw_cfg.show_metrics and not metrics_primed:
                                for metric in sw_cfg.metrics_items:
                                    if metric in {"cpu", "network"}:
                                        self._metrics_reader.read_metric_value(metric)
                                metrics_primed = True
                            if active_mode == SmallWindowMode.STATS:
                                await self._service._device.set_buttons(
                                    (
                                        _small_window_metrics_button(
                                            background_color=sw_cfg.background_color,
                                            metric_lines=self._custom_metric_lines(
                                                sw_cfg.metrics_items
                                            ),
                                        ),
                                    ),
                                    partial=True,
                                )
                            else:
                                await self._service._device.set_buttons(
                                    (
                                        _small_window_clock_button(
                                            background_color=sw_cfg.background_color,
                                            time_str=self._wire_time_string(
                                                sw_cfg.time_format
                                            ),
                                        ),
                                    ),
                                    partial=True,
                                )
                        else:
                            if active_mode != desired_mode:
                                await self._service._device.set_small_window_mode(
                                    desired_mode
                                )
                                device_mode = desired_mode
                                active_mode = desired_mode
                                mode_started_at = now
                                metrics_primed = False
                                if _rotates_small_window(sw_cfg):
                                    next_mode_switch_in = sw_cfg.rotate_every_s
                            if sw_cfg.show_metrics and not metrics_primed:
                                self._metrics_reader.read_cpu_percent()
                                metrics_primed = True
                            if active_mode == SmallWindowMode.STATS:
                                cpu: int | None = self._metrics_reader.read_cpu_percent()
                                mem: int | None = self._metrics_reader.read_memory_percent()
                                time_str = self._wire_time_string(sw_cfg.time_format)
                                await self._service._device.set_small_window_data(
                                    cpu=cpu,
                                    mem=mem,
                                    gpu=0,
                                    time_str=time_str,
                                )
                            else:
                                time_str = self._wire_time_string(sw_cfg.time_format)
                                await self._service._device.set_small_window_data(
                                    cpu=0,
                                    mem=0,
                                    gpu=0,
                                    time_str=time_str,
                                )
                        timeout = sw_cfg.interval_s
                        if next_mode_switch_in is not None:
                            timeout = min(timeout, max(next_mode_switch_in, 0.01))
                    else:
                        if device_mode != SmallWindowMode.BACKGROUND:
                            await self._service._device.set_small_window_mode(
                                SmallWindowMode.BACKGROUND
                            )
                            device_mode = SmallWindowMode.BACKGROUND
                            active_mode = SmallWindowMode.BACKGROUND
                            mode_started_at = None
                            metrics_primed = False
                        await self._service._device.keep_alive()
                        timeout = self._heartbeat_interval_s
                except Exception as exc:
                    logger.warning("status_loop_tick_failed", error=str(exc))
                    timeout = self._heartbeat_interval_s
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=timeout)
        finally:
            logger.info("status_loop_stopped")

    async def _event_loop(self, stop_event: asyncio.Event) -> None:
        async for event in self._service.listen():
            if stop_event.is_set():
                break
            if not isinstance(event, ButtonEvent):
                continue
            logger.info(
                "button_event_received",
                index=event.index,
                pressed=event.pressed,
                state=event.state,
                page=self._current_page,
            )
            if not event.pressed:
                continue  # react on press only; could be made configurable
            button = self._config.button_at(self._current_page, event.index)
            if button is None or button.action is None:
                logger.debug(
                    "no_action_bound",
                    index=event.index,
                    page=self._current_page,
                )
                continue
            action_fields = _action_log_fields(button.action)
            logger.info(
                "button_action_dispatch",
                index=event.index,
                page=self._current_page,
                **action_fields,
            )
            # Paging is handled by the daemon, not the runner — keeps the
            # runner ignorant of deck-internal state and prevents a
            # subprocess from being spawned for a page switch.
            if isinstance(button.action, SwitchPageAction):
                await self.switch_to(button.action.page)
                logger.info(
                    "button_action_completed",
                    index=event.index,
                    page=self._current_page,
                    result="page_switched",
                    **action_fields,
                )
                continue
            try:
                await self._runner.run(button.action)
                logger.info(
                    "button_action_accepted",
                    index=event.index,
                    page=self._current_page,
                    **action_fields,
                )
            except Exception as exc:
                logger.error(
                    "action_failed",
                    index=event.index,
                    page=self._current_page,
                    **action_fields,
                    action=repr(button.action),
                    error=str(exc),
                )

__all__ = ["DEFAULT_HEARTBEAT_INTERVAL_S", "DeckDaemon"]
