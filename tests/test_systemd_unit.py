"""Sanity tests for the shipped systemd user unit.

Why these exist:
    * The unit file is hand-written ini and very easy to break silently —
      a stray typo in ``ExecStart`` or a missing ``[Install]`` section
      will only surface on a user's machine, not in CI.
    * We can't call ``systemd-analyze`` from this test environment, so we
      parse the file with Python's ``configparser`` (systemd's .service
      format is ini-compatible for our purposes) and assert the shape
      the install docs promise.
"""

from __future__ import annotations

import configparser
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
UNIT_PATH = REPO_ROOT / "systemd" / "ulanzi-linux.service"
INSTALL_SCRIPT = REPO_ROOT / "systemd" / "install.sh"
AUTOSTART_PATH = REPO_ROOT / "autostart" / "ulanzi-linux-session-agent.desktop"


@pytest.fixture(scope="module")
def unit() -> configparser.ConfigParser:
    assert UNIT_PATH.exists(), f"missing unit file: {UNIT_PATH}"
    cp = configparser.ConfigParser(
        # systemd allows repeated keys (e.g. Environment=, After=) — not
        # something we use yet, but this keeps parsing permissive.
        strict=False,
        interpolation=None,
    )
    cp.read(UNIT_PATH, encoding="utf-8")
    return cp


def test_unit_has_required_sections(unit: configparser.ConfigParser) -> None:
    for section in ("Unit", "Service", "Install"):
        assert unit.has_section(section), f"[{section}] missing"


def test_unit_description_and_docs(unit: configparser.ConfigParser) -> None:
    assert "Ulanzi" in unit.get("Unit", "Description")
    assert unit.get("Unit", "Documentation").startswith("http")


def test_service_exec_start_points_to_entry_point(
    unit: configparser.ConfigParser,
) -> None:
    exec_start = unit.get("Service", "ExecStart")
    # %h is the user-home specifier — portable across accounts.
    assert "%h/.local/bin/ulanzi-linux" in exec_start
    assert " daemon " in exec_start
    assert exec_start.endswith("deck.yaml")
    # Structured logging is the contract for this unit.
    assert "--json-logs" in exec_start
    # Hot-reload must stay on — the doc promises edits-take-effect.
    assert "--no-watch" not in exec_start


def test_service_restart_policy_is_sane(
    unit: configparser.ConfigParser,
) -> None:
    assert unit.get("Service", "Restart") == "on-failure"
    # RestartSec must be >=1 to avoid CPU-melting flap loops.
    assert int(unit.get("Service", "RestartSec")) >= 1
    # StartLimit keeps a permanently-broken install from respawning forever.
    assert int(unit.get("Service", "StartLimitBurst")) >= 1


def test_service_stop_behavior(unit: configparser.ConfigParser) -> None:
    # The daemon reacts to SIGTERM via stop_event — systemd must send it.
    assert unit.get("Service", "KillSignal") == "SIGTERM"
    # Give the event loop room to cancel tasks and flush the last HID
    # packet before escalating to SIGKILL.
    assert int(unit.get("Service", "TimeoutStopSec")) >= 5


def test_service_environment_has_unbuffered_python(
    unit: configparser.ConfigParser,
) -> None:
    env = unit.get("Service", "Environment")
    assert "PYTHONUNBUFFERED=1" in env


def test_install_wanted_by_default_target(
    unit: configparser.ConfigParser,
) -> None:
    # User units enabled via ``systemctl --user enable`` must hook into
    # ``default.target`` — there's no graphical.target in the user
    # manager's target tree on most distros.
    assert unit.get("Install", "WantedBy") == "default.target"


def test_install_script_is_executable() -> None:
    assert INSTALL_SCRIPT.exists(), "install.sh missing"
    mode = INSTALL_SCRIPT.stat().st_mode
    # Owner execute bit.
    assert mode & 0o100, "install.sh is not executable"


def test_install_script_references_correct_unit_name() -> None:
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    # If the unit name ever drifts from the .service file, installs break.
    assert 'UNIT_NAME="ulanzi-linux.service"' in text
    # Script targets the user systemd tree, not system-wide.
    assert "systemctl --user" in text
    assert 'AUTOSTART_NAME="ulanzi-linux-session-agent.desktop"' in text
    assert 'systemctl --user restart "${UNIT_NAME}"' in text
    assert 'desktop-install "${DECK_YAML}"' in text
    assert 'DESKTOP_ENTRY_DST="${APPLICATIONS_DIR}/ulanzi-linux.desktop"' in text


def test_autostart_desktop_file_has_expected_shape() -> None:
    assert AUTOSTART_PATH.exists(), f"missing autostart file: {AUTOSTART_PATH}"
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(AUTOSTART_PATH, encoding="utf-8")

    assert cp.has_section("Desktop Entry")
    assert cp.get("Desktop Entry", "Type") == "Application"
    assert cp.get("Desktop Entry", "Terminal") == "false"
    assert "session-agent" in cp.get("Desktop Entry", "Exec")
