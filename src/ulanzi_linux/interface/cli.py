"""Command line interface for ulanzi-linux.

Entry points:
    * ``ulanzi-linux devices``   — list connected D200 units.
    * ``ulanzi-linux listen``    — stream button events live.
    * ``ulanzi-linux brightness`` — set LCD brightness (0-100).

The CLI is intentionally thin: it parses arguments, calls into ``DeckService``
and renders results. Business logic lives in the application layer.
"""

from __future__ import annotations

import asyncio
import signal
from contextlib import suppress
from pathlib import Path
from typing import NoReturn

import click
import structlog
from rich.console import Console
from rich.table import Table

from ulanzi_linux import __version__
from ulanzi_linux.application.action_runner import ActionRunner
from ulanzi_linux.application.artifacts import (
    build_default_page_bundle,
    timestamp_token,
    versioned_output_path,
)
from ulanzi_linux.application.config_loader import load_deck_config
from ulanzi_linux.application.config_watcher import ConfigWatcher
from ulanzi_linux.application.daemon import DeckDaemon
from ulanzi_linux.application.deck_service import DeckService
from ulanzi_linux.application.session_agent import GraphicalSessionAgentServer
from ulanzi_linux.domain.events import ButtonEvent, DeviceInfoEvent
from ulanzi_linux.infrastructure.hid_transport import (
    DeviceNotFoundError,
    DeviceOpenError,
    enumerate_hid_devices,
)
from ulanzi_linux.infrastructure.ulanzi_d200 import D200_SPEC
from ulanzi_linux.observability import configure_logging

console = Console()
logger = structlog.get_logger(__name__)


def _bail(message: str, *, code: int = 1) -> NoReturn:
    console.print(f"[bold red]error:[/] {message}")
    raise SystemExit(code)


@click.group()
@click.version_option(__version__, prog_name="ulanzi-linux")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable DEBUG logging.",
)
@click.option(
    "--json-logs",
    is_flag=True,
    default=False,
    help="Force JSON log output (default: auto-detect TTY).",
)
def cli(verbose: bool, json_logs: bool) -> None:
    """Control the Ulanzi Stream Pad D200 from Linux."""
    configure_logging(
        level="DEBUG" if verbose else "INFO",
        json_output=True if json_logs else None,
    )


# ---------------------------------------------------------------------- #
# devices                                                                 #
# ---------------------------------------------------------------------- #


@cli.command("devices")
def devices_command() -> None:
    """List all Ulanzi D200 devices currently attached."""
    matches = list(
        enumerate_hid_devices(
            vendor_id=D200_SPEC.usb_vendor_id,
            product_id=D200_SPEC.usb_product_id,
        )
    )

    if not matches:
        console.print("[yellow]No Ulanzi D200 devices detected.[/]")
        console.print(
            f"Expected VID={D200_SPEC.usb_vendor_id:#06x}, "
            f"PID={D200_SPEC.usb_product_id:#06x}."
        )
        return

    table = Table(title="Ulanzi D200 devices")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Manufacturer")
    table.add_column("Product")
    table.add_column("Serial")
    table.add_column("Interface", justify="right")
    table.add_column("Path", overflow="fold")

    for idx, entry in enumerate(matches):
        table.add_row(
            str(idx),
            str(entry.get("manufacturer_string") or "-"),
            str(entry.get("product_string") or "-"),
            str(entry.get("serial_number") or "-"),
            str(entry.get("interface_number", "-")),
            str(entry.get("path", b"").decode("utf-8", errors="replace")),
        )

    console.print(table)


# ---------------------------------------------------------------------- #
# listen                                                                  #
# ---------------------------------------------------------------------- #


@cli.command("listen")
@click.option(
    "--events",
    "max_events",
    type=int,
    default=None,
    help="Stop after N events (default: run until Ctrl-C).",
)
def listen_command(max_events: int | None) -> None:
    """Stream button events from the deck to the terminal."""
    try:
        asyncio.run(_listen_async(max_events))
    except DeviceNotFoundError as exc:
        _bail(str(exc))
    except DeviceOpenError as exc:
        _bail(f"{exc}\nTry: check udev rules or that you are in the 'plugdev' group.")


async def _listen_async(max_events: int | None) -> None:
    stop_event = asyncio.Event()

    def _request_stop() -> None:
        if not stop_event.is_set():
            stop_event.set()
            console.print("[dim]stopping...[/]")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, _request_stop)

    async with DeckService.open_default() as service:
        console.print(
            f"[green]connected[/] to [bold]{service.spec.name}[/] "
            f"— waiting for button events (Ctrl-C to stop)."
        )

        count = 0
        async for event in service.listen():
            _render_event(event)
            count += 1
            if max_events is not None and count >= max_events:
                break
            if stop_event.is_set():
                break


def _render_event(event: ButtonEvent | DeviceInfoEvent) -> None:
    timestamp = event.occurred_at.isoformat(timespec="milliseconds")
    if isinstance(event, ButtonEvent):
        kind = "[green]press  [/]" if event.pressed else "[yellow]release[/]"
        console.print(
            f"[dim]{timestamp}[/] {kind} button=[bold]{event.index:>2}[/] "
            f"state={event.state:#04x}"
        )
    else:
        console.print(f"[dim]{timestamp}[/] [cyan]device_info[/] {event.info}")


# ---------------------------------------------------------------------- #
# brightness                                                              #
# ---------------------------------------------------------------------- #


@cli.command("brightness")
@click.argument("value", type=click.IntRange(0, 100))
def brightness_command(value: int) -> None:
    """Set the LCD brightness (0-100)."""
    try:
        asyncio.run(_brightness_async(value))
    except DeviceNotFoundError as exc:
        _bail(str(exc))
    except DeviceOpenError as exc:
        _bail(str(exc))


async def _brightness_async(value: int) -> None:
    async with DeckService.open_default() as service:
        await service.set_brightness(value)
        console.print(f"[green]brightness set to {value}[/]")


# ---------------------------------------------------------------------- #
# push-config                                                             #
# ---------------------------------------------------------------------- #


@cli.command("push-config")
@click.argument("config_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--partial", is_flag=True, help="Additive update (keep other buttons).")
@click.option(
    "--save-firmware",
    is_flag=True,
    help="Also save the generated ZIP payload next to the YAML config.",
)
def push_config_command(
    config_path: str,
    partial: bool,
    save_firmware: bool,
) -> None:
    """Upload icons and layout from a YAML config to the deck."""
    try:
        asyncio.run(_push_config_async(config_path, partial, save_firmware))
    except DeviceNotFoundError as exc:
        _bail(str(exc))
    except DeviceOpenError as exc:
        _bail(str(exc))


async def _push_config_async(
    config_path: str,
    partial: bool,
    save_firmware: bool,
) -> None:
    cfg = load_deck_config(config_path)
    saved_bundle: Path | None = None
    if save_firmware:
        saved_bundle = versioned_output_path(
            Path(config_path).expanduser().resolve(),
            token=timestamp_token(),
            label="firmware",
            extension=".zip",
        )
        saved_bundle.write_bytes(build_default_page_bundle(cfg, partial=partial))
    # push-config is a one-shot layout upload: we push the default page plus
    # any fixed buttons. For paging behaviour at runtime, use ``daemon``.
    layout = cfg.buttons_for(cfg.default_page)
    async with DeckService.open_default() as service:
        await service._device.set_buttons(layout, partial=partial)
    message = (
        f"[green]pushed page '{cfg.default_page}'[/] "
        f"— {len(layout)} buttons ({len(cfg.fixed_buttons)} fixed) "
        f"({'partial' if partial else 'full'}) from {config_path}"
    )
    if saved_bundle is not None:
        message += f"\n[cyan]bundle salvo em[/] {saved_bundle}"
    console.print(message)


# ---------------------------------------------------------------------- #
# daemon                                                                  #
# ---------------------------------------------------------------------- #


@cli.command("daemon")
@click.argument("config_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--skip-sync", is_flag=True, help="Do not re-upload layout on start.")
@click.option(
    "--no-watch",
    is_flag=True,
    help="Disable YAML hot-reload (watch is on by default).",
)
def daemon_command(config_path: str, skip_sync: bool, no_watch: bool) -> None:
    """Run the event-to-action daemon against a YAML config."""
    try:
        asyncio.run(_daemon_async(config_path, skip_sync, watch=not no_watch))
    except DeviceNotFoundError as exc:
        _bail(str(exc))
    except DeviceOpenError as exc:
        _bail(str(exc))


async def _daemon_async(
    config_path: str, skip_sync: bool, *, watch: bool
) -> None:
    cfg = load_deck_config(config_path)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    async with DeckService.open_default() as service:
        daemon = DeckDaemon(service, cfg, ActionRunner())
        if not skip_sync:
            await daemon.sync_layout()

        watcher: ConfigWatcher | None = None
        if watch:
            # The watcher is disk-only glue; the reload decision and
            # atomic swap live in the daemon itself.
            watcher = ConfigWatcher(
                config_path, on_change=daemon.reload_config
            )

        page_list = ", ".join(cfg.pages.keys())
        console.print(
            f"[green]daemon running[/] — pages=[{page_list}] "
            f"default='{cfg.default_page}' fixed={len(cfg.fixed_buttons)} "
            f"watch={'on' if watch else 'off'}. Ctrl-C to stop."
        )
        await daemon.run(stop_event=stop, watcher=watcher)


# ---------------------------------------------------------------------- #
# session-agent                                                           #
# ---------------------------------------------------------------------- #


@cli.command("session-agent")
def session_agent_command() -> None:
    """Run the graphical-session bridge for shell, URL and shortcut actions."""
    try:
        asyncio.run(_session_agent_async())
    except ValueError as exc:
        _bail(str(exc))


async def _session_agent_async() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    server = GraphicalSessionAgentServer()
    console.print(
        f"[green]session-agent running[/] — socket='{server.socket_path}'. Ctrl-C to stop."
    )
    await server.serve(stop_event=stop)


# ---------------------------------------------------------------------- #
# gui                                                                     #
# ---------------------------------------------------------------------- #


@cli.command("gui")
@click.argument("config_path", type=click.Path(dir_okay=False))
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Bind address. Anything other than loopback prints a warning.",
)
@click.option(
    "--port",
    type=click.IntRange(1, 65535),
    default=8765,
    show_default=True,
    help="TCP port for the web editor.",
)
def gui_command(config_path: str, host: str, port: int) -> None:
    """Launch a localhost web editor for the YAML deck config.

    The editor is decoupled from the daemon: it only reads/validates/writes
    the YAML file. If a daemon is running, its ``ConfigWatcher`` picks the
    change up within ~1 s. If no daemon is running, the editor still works
    — useful for authoring a config offline.
    """
    try:
        from ulanzi_linux.interface.web.server import serve
    except ImportError as exc:
        _bail(
            "web UI dependencies not installed. Run:\n"
            "  pip install '.[web]'\n"
            f"({exc})"
        )

    serve(config_path, host=host, port=port)


if __name__ == "__main__":
    cli()
