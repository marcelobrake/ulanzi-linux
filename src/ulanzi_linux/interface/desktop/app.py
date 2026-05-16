"""Desktop launcher for the local editor using pywebview."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import time
import webbrowser
from contextlib import suppress
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_WINDOW_TITLE = "Ulanzi Linux"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "ulanzi" / "deck.yaml"
DEFAULT_APPLICATIONS_DIR = Path.home() / ".local" / "share" / "applications"
DEFAULT_ICON_DIR = Path.home() / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"


def _configure_qt_platform() -> None:
    if os.environ.get("QT_QPA_PLATFORM"):
        return
    if os.environ.get("XDG_SESSION_TYPE") != "wayland":
        return
    if not os.environ.get("WAYLAND_DISPLAY"):
        return
    os.environ["QT_QPA_PLATFORM"] = "wayland"


def _asset_icon_path() -> Path:
    return Path(__file__).parent / "assets" / "ulanzi-linux-desktop.svg"


def _quoted_exec_arg(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def desktop_entry_contents(
    *,
    config_path: Path,
    icon_path: Path,
    executable: str = "ulanzi-linux",
) -> str:
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Version=1.0",
            f"Name={DEFAULT_WINDOW_TITLE}",
            "Comment=Desktop editor for the Ulanzi D200 deck configuration",
            f"Exec={executable} desktop {_quoted_exec_arg(str(config_path))}",
            f"TryExec={executable}",
            f"Icon={icon_path}",
            "Terminal=false",
            "Categories=Utility;Graphics;",
            "Keywords=Ulanzi;Stream Deck;D200;Editor;",
            "StartupNotify=true",
        ]
    ) + "\n"


def install_desktop_launcher(
    config_path: Path = DEFAULT_CONFIG_PATH,
    *,
    applications_dir: Path = DEFAULT_APPLICATIONS_DIR,
    icons_dir: Path = DEFAULT_ICON_DIR,
) -> tuple[Path, Path]:
    applications_dir.mkdir(parents=True, exist_ok=True)
    icons_dir.mkdir(parents=True, exist_ok=True)

    icon_target = icons_dir / "ulanzi-linux.svg"
    shutil.copyfile(_asset_icon_path(), icon_target)

    entry_path = applications_dir / "ulanzi-linux.desktop"
    entry_path.write_text(
        desktop_entry_contents(
            config_path=config_path.expanduser().resolve(),
            icon_path=icon_target,
        ),
        encoding="utf-8",
    )
    entry_path.chmod(0o755)

    desktop_database = shutil.which("update-desktop-database")
    if desktop_database is not None:
        with suppress(OSError, subprocess.CalledProcessError):
            subprocess.run(
                [desktop_database, str(applications_dir)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    return entry_path, icon_target


def _reserve_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


class _EditorServer:
    def __init__(self, config_path: Path, *, host: str, port: int) -> None:
        self.config_path = config_path
        self.host = host
        self.port = port
        self._thread: threading.Thread | None = None
        self._server = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        import uvicorn

        from ulanzi_linux.interface.web.app import create_app

        app = create_app(self.config_path)
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()

        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if getattr(self._server, "started", False):
                return
            if self._thread and not self._thread.is_alive():
                break
            time.sleep(0.05)
        raise RuntimeError("desktop editor server failed to start")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5.0)


def _build_tray_image() -> object:
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (13, 17, 24, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((6, 6, 58, 58), radius=12, fill=(18, 24, 33, 255), outline=(121, 221, 248, 255), width=2)
    for row in range(3):
        for col in range(3):
            left = 14 + (col * 14)
            top = 14 + (row * 14)
            draw.rounded_rectangle((left, top, left + 8, top + 8), radius=3, fill=(243, 201, 108, 255))
    return image


def _start_tray(url: str, window_holder: dict[str, object | None]) -> object | None:
    try:
        import pystray
    except ImportError:
        return None

    def open_window(icon: object, item: object) -> None:
        del icon, item
        window = window_holder.get("window")
        if window is not None:
            with suppress(Exception):
                getattr(window, "show")()
            with suppress(Exception):
                getattr(window, "restore")()
        else:
            webbrowser.open(url)

    def open_browser(icon: object, item: object) -> None:
        del icon, item
        webbrowser.open(url)

    def quit_all(icon: object, item: object) -> None:
        del item
        window = window_holder.get("window")
        if window is not None:
            with suppress(Exception):
                getattr(window, "destroy")()
        with suppress(Exception):
            icon.stop()

    icon = pystray.Icon(
        "ulanzi-linux",
        _build_tray_image(),
        DEFAULT_WINDOW_TITLE,
        menu=pystray.Menu(
            pystray.MenuItem("Mostrar editor", open_window),
            pystray.MenuItem("Abrir no navegador", open_browser),
            pystray.MenuItem("Sair", quit_all),
        ),
    )
    threading.Thread(target=icon.run, daemon=True).start()
    return icon


def launch_desktop_app(config_path: str | Path = DEFAULT_CONFIG_PATH) -> None:
    _configure_qt_platform()
    import webview

    resolved_config = Path(config_path).expanduser().resolve()
    server = _EditorServer(
        resolved_config,
        host=DEFAULT_HOST,
        port=_reserve_port(DEFAULT_HOST),
    )
    server.start()

    tray_icon: object | None = None
    window_holder: dict[str, object | None] = {"window": None}
    try:
        tray_icon = _start_tray(server.url, window_holder)
        window_holder["window"] = webview.create_window(
            DEFAULT_WINDOW_TITLE,
            server.url,
            width=1480,
            height=980,
            min_size=(1180, 800),
            text_select=True,
            confirm_close=True,
        )
        webview.start(gui="qt", debug=False)
    finally:
        if tray_icon is not None:
            with suppress(Exception):
                tray_icon.stop()
        server.stop()


__all__ = [
    "DEFAULT_APPLICATIONS_DIR",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_ICON_DIR",
    "desktop_entry_contents",
    "install_desktop_launcher",
    "launch_desktop_app",
]