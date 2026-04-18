"""Tests for the FastAPI web editor.

These exercise the HTTP surface via ``TestClient`` (no real network), and
hammer the atomic-write path with malformed YAML to make sure we never
leave a corrupt config on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")  # skip cleanly when [web] extra is absent
from fastapi.testclient import TestClient

from ulanzi_linux.interface.web.app import (
    _atomic_write,
    _validate_yaml_text,
    create_app,
)


VALID_YAML = """\
default_page: main
small_window:
  enabled: true
  interval_s: 2.0
pages:
  main:
    buttons:
      - index: 0
        label: Term
        action: { type: shell, cmd: gnome-terminal }
  media:
    buttons:
      - index: 0
        label: Play
        action: { type: shortcut, keys: XF86AudioPlay }
fixed_buttons:
  - index: 10
    label: Main
    action: { type: switch_page, page: main }
"""

BROKEN_YAML_UNKNOWN_ACTION = """\
default_page: main
pages:
  main:
    buttons:
      - index: 0
        label: Bogus
        action: { type: self_destruct }
"""

BROKEN_YAML_MISSING_DEFAULT_PAGE = """\
default_page: ghost
pages:
  main:
    buttons: []
"""


# ---------------------------------------------------------------------- #
# Pure helpers                                                            #
# ---------------------------------------------------------------------- #


def test_validate_accepts_valid_yaml() -> None:
    result = _validate_yaml_text(VALID_YAML)
    assert result.ok is True
    assert result.error is None
    assert result.default_page == "main"
    assert {p.name for p in result.pages} == {"main", "media"}
    assert result.small_window_enabled is True
    assert result.fixed_button_indices == [10]


def test_validate_rejects_unknown_action_type() -> None:
    result = _validate_yaml_text(BROKEN_YAML_UNKNOWN_ACTION)
    assert result.ok is False
    assert result.error is not None
    assert "self_destruct" in result.error


def test_validate_rejects_missing_default_page() -> None:
    result = _validate_yaml_text(BROKEN_YAML_MISSING_DEFAULT_PAGE)
    assert result.ok is False
    assert "ghost" in (result.error or "")


def test_atomic_write_replaces_target(tmp_path: Path) -> None:
    target = tmp_path / "deck.yaml"
    target.write_text("old\n")
    _atomic_write(target, "new\n")
    assert target.read_text() == "new\n"
    # No lingering temp artifacts.
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".deck.yaml.")]
    assert leftovers == []


# ---------------------------------------------------------------------- #
# API                                                                     #
# ---------------------------------------------------------------------- #


@pytest.fixture
def client(tmp_path: Path) -> tuple[TestClient, Path]:
    config_path = tmp_path / "deck.yaml"
    config_path.write_text(VALID_YAML, encoding="utf-8")
    app = create_app(config_path)
    return TestClient(app), config_path


def test_health_reports_config_and_version(
    client: tuple[TestClient, Path],
) -> None:
    c, path = client
    r = c.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["config_exists"] is True
    # Absolute-path invariant — the client displays this in the UI header.
    assert body["config_path"].endswith(path.name)
    assert isinstance(body["devices_found"], int)


def test_get_config_returns_text_and_metadata(
    client: tuple[TestClient, Path],
) -> None:
    c, path = client
    r = c.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["content"].startswith("default_page: main")
    assert body["size"] == path.stat().st_size


def test_get_config_returns_404_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "does-not-exist.yaml"
    app = create_app(path)
    c = TestClient(app)
    r = c.get("/api/config")
    assert r.status_code == 404


def test_validate_endpoint_accepts_valid_yaml(
    client: tuple[TestClient, Path],
) -> None:
    c, _ = client
    r = c.post("/api/config/validate", json={"content": VALID_YAML})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["default_page"] == "main"


def test_validate_endpoint_returns_error_for_bad_yaml(
    client: tuple[TestClient, Path],
) -> None:
    c, _ = client
    r = c.post(
        "/api/config/validate", json={"content": BROKEN_YAML_UNKNOWN_ACTION}
    )
    assert r.status_code == 200  # validate never 4xx's — diagnostic in body
    body = r.json()
    assert body["ok"] is False
    assert "self_destruct" in body["error"]


def test_put_config_persists_valid_yaml(
    client: tuple[TestClient, Path],
) -> None:
    c, path = client
    new = VALID_YAML + "\n# edited via web\n"
    r = c.put("/api/config", json={"content": new})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert path.read_text() == new


def test_put_config_rejects_bad_yaml_and_preserves_disk(
    client: tuple[TestClient, Path],
) -> None:
    c, path = client
    before = path.read_text()
    r = c.put("/api/config", json={"content": BROKEN_YAML_UNKNOWN_ACTION})
    # 422 = validation error; diagnostic carried in body.
    assert r.status_code == 422
    body = r.json()
    assert body["ok"] is False
    # Disk must be untouched — that's the whole point of atomic write +
    # validate-before-persist.
    assert path.read_text() == before


def test_put_config_creates_parent_directory(tmp_path: Path) -> None:
    # Simulate first-time save on a fresh machine without ``~/.config/ulanzi``.
    nested = tmp_path / "ulanzi" / "deck.yaml"
    app = create_app(nested)
    c = TestClient(app)
    r = c.put("/api/config", json={"content": VALID_YAML})
    assert r.status_code == 200
    assert nested.exists()
    assert nested.read_text() == VALID_YAML


def test_index_and_static_are_served(client: tuple[TestClient, Path]) -> None:
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200
    assert "<title>" in r.text and "ulanzi-linux" in r.text
    assert "/static/app.js" in r.text
    assert "alpinejs" in r.text
    assert r.text.index("/static/app.js") < r.text.index("alpinejs")
    # Static mount exposes the CSS/JS files.
    r = c.get("/static/app.css")
    assert r.status_code == 200
    assert "--bg:" in r.text
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert "window.editorApp = function editorApp()" in r.text
    assert "CodeMirror unavailable, falling back to textarea" in r.text
