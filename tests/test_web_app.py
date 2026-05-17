"""Tests for the FastAPI web editor.

These exercise the HTTP surface via ``TestClient`` (no real network), and
hammer the atomic-write path with malformed YAML to make sure we never
leave a corrupt config on disk.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image

pytest.importorskip("fastapi")  # skip cleanly when [web] extra is absent
from fastapi.testclient import TestClient

from ulanzi_linux.interface.web.app import (
    _atomic_write,
    _validate_yaml_text,
    create_app,
)

VALID_YAML = (
    "default_page: main\n"
    "small_window:\n"
    "  enabled: true\n"
    "  interval_s: 2.0\n"
    "  show_metrics: true\n"
    "pages:\n"
    "  main:\n"
    "    buttons:\n"
    "      - index: 0\n"
    "        label: Term\n"
    "        action: { type: shell, cmd: gnome-terminal }\n"
    "  media:\n"
    "    buttons:\n"
    "      - index: 0\n"
    "        label: Play\n"
    "        action: { type: shortcut, keys: XF86AudioPlay }\n"
    "fixed_buttons:\n"
    "  - index: 10\n"
    "    label: Main\n"
    "    action: { type: switch_page, page: main }\n"
)

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


def test_get_editor_returns_structured_config(
    client: tuple[TestClient, Path],
) -> None:
    c, path = client
    r = c.get("/api/editor")
    assert r.status_code == 200
    body = r.json()
    assert body["path"] == str(path)
    assert body["default_page"] == "main"
    assert body["pages"][0]["name"] == "main"
    assert body["small_window"]["show_metrics"] is True
    assert body["small_window"]["rotate_every_s"] is None
    assert body["small_window"]["background_color"] == "#000000"
    assert body["pages"][0]["buttons"][0]["action"]["command_id"] == ""
    assert body["pages"][0]["buttons"][0]["text_style"]["background_color"] == "#111827"
    assert body["versioned_config_path"] is None
    assert body["saved_firmware_bundle_path"] is None


def test_small_window_preview_returns_live_payload(
    client: tuple[TestClient, Path],
) -> None:
    c, _ = client
    r = c.get("/api/small-window/preview", params={"time_format": "%H:%M"})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["time_text"], str)
    assert isinstance(body["cpu_percent"], int)
    assert isinstance(body["mem_percent"], int)
    assert body["gpu_percent"] == 0


def test_builtin_assets_catalog_returns_many_icons(
    client: tuple[TestClient, Path],
) -> None:
    c, _ = client
    r = c.get("/api/builtin-assets")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 1000
    assert body["items"]
    assert "family" in body["items"][0]
    assert body["items"][0]["preview_url"].startswith("/api/builtin-asset")


def test_builtin_assets_catalog_exposes_emoji_entries_when_available(
    client: tuple[TestClient, Path],
) -> None:
    c, _ = client
    body = c.get("/api/builtin-assets").json()
    if not any(item["family"] == "emoji" for item in body["items"]):
        pytest.skip("emoji assets not available on this host")

    emoji_item = next(item for item in body["items"] if item["family"] == "emoji")
    assert emoji_item["style"] == "emoji"
    preview = c.get(emoji_item["preview_url"])
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"


def test_import_builtin_asset_materializes_local_png(
    client: tuple[TestClient, Path],
) -> None:
    c, _ = client
    catalog = c.get("/api/builtin-assets").json()
    asset_id = catalog["items"][0]["asset_id"]

    r = c.post("/api/builtin-assets/import", json={"asset_id": asset_id})
    assert r.status_code == 200
    body = r.json()
    saved = Path(body["path"]).expanduser()
    assert saved.exists()
    assert saved.suffix == ".png"
    assert body["preview_url"].startswith("/api/asset?path=")


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


def test_validate_endpoint_accepts_predefined_command_yaml(
    client: tuple[TestClient, Path],
) -> None:
    c, _ = client
    yaml_text = (
        "default_page: main\n"
        "pages:\n"
        "  main:\n"
        "    buttons:\n"
        "      - index: 5\n"
        "        action:\n"
        "          type: predefined_command\n"
        "          command_id: media_play_pause\n"
    )
    r = c.post("/api/config/validate", json={"content": yaml_text})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True


def test_editor_validate_accepts_info_window_action_slot(
    client: tuple[TestClient, Path],
) -> None:
    c, _ = client
    payload = c.get("/api/editor").json()
    payload["fixed_buttons"].append(
        {
            "index": 13,
            "label": "Wide",
            "icon_path": None,
            "action": {
                "type": "url",
                "cmd": "",
                "keys": "",
                "url": "https://example.com",
                "page": "",
            },
        }
    )
    r = c.post("/api/editor/validate", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True


def test_put_editor_persists_info_window_action_without_visuals(
    client: tuple[TestClient, Path],
) -> None:
    c, path = client
    payload = c.get("/api/editor").json()
    payload["fixed_buttons"].append(
        {
            "index": 13,
            "label": "Ignored",
            "icon_path": "~/.config/ulanzi/icons/ignored.png",
            "action": {
                "type": "url",
                "cmd": "",
                "keys": "",
                "url": "https://example.com/info",
                "page": "",
            },
        }
    )

    r = c.put("/api/editor", json=payload)
    assert r.status_code == 200
    saved = path.read_text()
    assert "index: 13" in saved
    assert "https://example.com/info" in saved
    assert "ignored.png" not in saved
    assert "label: Ignored" not in saved


def test_put_editor_persists_fixed_info_window_placeholder(
    client: tuple[TestClient, Path],
) -> None:
    c, path = client
    payload = c.get("/api/editor").json()
    payload["fixed_buttons"].append(
        {
            "index": 13,
            "label": "",
            "icon_path": None,
            "action": {
                "type": "none",
                "cmd": "",
                "keys": "",
                "command_id": "",
                "url": "",
                "page": "",
            },
            "text_style": {
                "background_color": "#111827",
                "text_color": "#F8FAFC",
                "bold": False,
                "italic": False,
                "underline": False,
                "font_family": "DejaVu Sans",
                "font_size": 30,
            },
        }
    )

    r = c.put("/api/editor", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert any(button["index"] == 13 for button in body["fixed_buttons"])
    saved = path.read_text()
    assert "fixed_buttons:" in saved
    assert "- index: 13" in saved


def test_put_editor_persists_text_style_for_text_only_button(
    client: tuple[TestClient, Path],
) -> None:
    c, path = client
    payload = c.get("/api/editor").json()
    payload["pages"][0]["buttons"][0]["icon_path"] = None
    payload["pages"][0]["buttons"][0]["text_style"] = {
        "background_color": "#112233",
        "text_color": "#F0E1D2",
        "bold": True,
        "italic": True,
        "underline": True,
        "font_family": "Liberation Serif",
        "font_size": 38,
    }

    r = c.put("/api/editor", json=payload)
    assert r.status_code == 200
    saved = path.read_text()
    assert "text_style:" in saved
    assert "background_color: '#112233'" in saved
    assert 'font_family: Liberation Serif' in saved


def test_put_editor_persists_predefined_command_action(
    client: tuple[TestClient, Path],
) -> None:
    c, path = client
    payload = c.get("/api/editor").json()
    payload["pages"][0]["buttons"][0]["action"] = {
        "type": "predefined_command",
        "cmd": "",
        "keys": "",
        "command_id": "display_screenshot_selection",
        "url": "",
        "page": "",
    }

    r = c.put("/api/editor", json=payload)
    assert r.status_code == 200
    saved = path.read_text()
    assert "type: predefined_command" in saved
    assert "command_id: display_screenshot_selection" in saved


def test_put_editor_can_also_save_firmware_bundle(
    client: tuple[TestClient, Path],
) -> None:
    c, _ = client
    payload = c.get("/api/editor").json()
    payload["save_firmware_bundle"] = True

    r = c.put("/api/editor", json=payload)
    assert r.status_code == 200
    body = r.json()

    versioned = Path(body["versioned_config_path"])
    bundle = Path(body["saved_firmware_bundle_path"])
    assert versioned.exists()
    assert bundle.exists()
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        assert "dummy.txt" in names
        assert "sentinel.txt" in names


def test_put_editor_persists_small_window_rotation(
    client: tuple[TestClient, Path],
) -> None:
    c, path = client
    payload = c.get("/api/editor").json()
    payload["small_window"]["rotate_every_s"] = 5.0

    r = c.put("/api/editor", json=payload)
    assert r.status_code == 200
    saved = path.read_text()
    assert "rotate_every_s: 5.0" in saved


def test_put_editor_persists_small_window_background_color(
    client: tuple[TestClient, Path],
) -> None:
    c, path = client
    payload = c.get("/api/editor").json()
    payload["small_window"]["background_color"] = "#224466"

    r = c.put("/api/editor", json=payload)
    assert r.status_code == 200
    saved = path.read_text()
    assert "background_color: '#224466'" in saved


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
    versioned = Path(body["versioned_config_path"])
    assert versioned.exists()
    assert versioned.read_text() == new
    assert body["saved_firmware_bundle_path"] is None


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


def test_upload_asset_normalizes_image_to_png_canvas(
    client: tuple[TestClient, Path],
) -> None:
    c, _ = client
    image = Image.new("RGB", (320, 80), (255, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    buffer.seek(0)

    r = c.post(
        "/api/assets",
        files={"file": ("wide-banner.jpg", buffer.getvalue(), "image/jpeg")},
    )
    assert r.status_code == 200
    body = r.json()
    saved = Path(body["path"]).expanduser()
    assert saved.suffix == ".png"

    with Image.open(saved) as normalized:
        assert normalized.size == (196, 196)
        assert normalized.getpixel((0, 0))[3] == 0
        center = normalized.getpixel((98, 98))
        assert center[0] >= 250
        assert center[1] <= 5
        assert center[2] <= 5


def test_index_and_static_are_served(client: tuple[TestClient, Path]) -> None:
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200
    assert "<title>" in r.text and "ulanzi-linux" in r.text
    assert "/static/app.js" in r.text
    assert "alpinejs" in r.text
    assert r.text.index("/static/app.js") < r.text.index("alpinejs")
    assert "Reset" in r.text
    assert "Comando pré-definido" in r.text
    # Static mount exposes the CSS/JS files.
    r = c.get("/static/app.css")
    assert r.status_code == 200
    assert "--bg:" in r.text
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert "window.editorApp = function editorApp()" in r.text
    assert "async resetDeck()" in r.text
    assert "Clique em Salvar no deck para aplicar." in r.text
    assert "predefined_command" in r.text
    assert "await this.saveDeck();" not in r.text
