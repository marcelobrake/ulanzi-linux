from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from ulanzi_linux.interface.cli import cli
from ulanzi_linux.interface.desktop.app import (
    desktop_entry_contents,
    install_desktop_launcher,
)


def test_desktop_entry_contains_exec_icon_and_categories(tmp_path: Path) -> None:
    config_path = tmp_path / "deck with spaces.yaml"
    content = desktop_entry_contents(
        config_path=config_path,
        icon_path=tmp_path / "ulanzi-linux.svg",
    )

    assert "Exec=ulanzi-linux desktop" in content
    assert f'"{config_path}"' in content
    assert f"Icon={tmp_path / 'ulanzi-linux.svg'}" in content
    assert "Categories=Utility;Graphics;" in content


def test_install_desktop_launcher_writes_entry_and_icon(tmp_path: Path) -> None:
    applications_dir = tmp_path / "applications"
    icons_dir = tmp_path / "icons"
    config_path = tmp_path / "deck.yaml"

    entry_path, icon_path = install_desktop_launcher(
        config_path,
        applications_dir=applications_dir,
        icons_dir=icons_dir,
    )

    assert entry_path.exists()
    assert icon_path.exists()
    assert entry_path.read_text(encoding="utf-8").startswith("[Desktop Entry]")
    assert "ulanzi-linux desktop" in entry_path.read_text(encoding="utf-8")


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