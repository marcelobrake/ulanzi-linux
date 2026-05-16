"""Desktop wrapper for the local Ulanzi editor."""

from ulanzi_linux.interface.desktop.app import (
    launch_desktop_app,
    install_desktop_launcher,
)

__all__ = ["install_desktop_launcher", "launch_desktop_app"]