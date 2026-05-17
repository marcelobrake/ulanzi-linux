from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from ulanzi_linux.interface.cli import cli
from ulanzi_linux.interface.desktop.app import (
    _configure_qt_platform,
    _default_launcher_executable,
    desktop_entry_contents,
    install_desktop_launcher,
)


def test_desktop_entry_contains_exec_icon_and_categories(tmp_path: Path) -> None:
    config_path = tmp_path / "deck with spaces.yaml"
    content = desktop_entry_contents(
        config_path=config_path,
        icon_path=tmp_path / "ulanzi-linux.svg",
        executable="/opt/ulanzi/bin/ulanzi-linux",
    )

    assert "Exec=/opt/ulanzi/bin/ulanzi-linux desktop" in content
    assert "TryExec=/opt/ulanzi/bin/ulanzi-linux" in content
    assert f'"{config_path}"' in content
    assert f"Icon={tmp_path / 'ulanzi-linux.svg'}" in content
    assert "Categories=Utility;" in content


def test_install_desktop_launcher_writes_entry_and_icon(tmp_path: Path) -> None:
    applications_dir = tmp_path / "applications"
    icons_dir = tmp_path / "icons"
    config_path = tmp_path / "deck.yaml"

    entry_path, icon_path = install_desktop_launcher(
        config_path,
        applications_dir=applications_dir,
        icons_dir=icons_dir,
        executable="/venv/bin/ulanzi-linux",
    )

    assert entry_path.exists()
    assert icon_path.exists()
    assert entry_path.read_text(encoding="utf-8").startswith("[Desktop Entry]")
    assert "Exec=/venv/bin/ulanzi-linux desktop" in entry_path.read_text(
        encoding="utf-8"
    )


def test_default_launcher_executable_prefers_current_python_sibling(
    monkeypatch, tmp_path: Path
) -> None:
    bin_dir = tmp_path / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    python_path = bin_dir / "python"
    python_path.write_text("", encoding="utf-8")
    ulanzi_path = bin_dir / "ulanzi-linux"
    ulanzi_path.write_text("", encoding="utf-8")

    monkeypatch.setattr("shutil.which", lambda _name: None)
    monkeypatch.setattr("sys.executable", str(python_path))

    assert _default_launcher_executable() == str(ulanzi_path)


def test_desktop_command_reports_missing_runtime_dependency(monkeypatch) -> None:
    def _raise_missing_dependency(config_path: str) -> None:
        del config_path
        raise ModuleNotFoundError("No module named 'webview'", name="webview")

    monkeypatch.setattr(
        "ulanzi_linux.interface.desktop.app.launch_desktop_app",
        _raise_missing_dependency,
    )

    result = CliRunner().invoke(cli, ["desktop", "deck.yaml"])

    assert result.exit_code == 1
    assert "pip install '.[desktop]'" in result.output
    assert "missing module: webview" in result.output


def test_configure_qt_platform_prefers_wayland_session(monkeypatch) -> None:
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

    _configure_qt_platform()

    assert __import__("os").environ["QT_QPA_PLATFORM"] == "wayland"


def test_configure_qt_platform_preserves_explicit_user_choice(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

    _configure_qt_platform()

    assert __import__("os").environ["QT_QPA_PLATFORM"] == "xcb"
