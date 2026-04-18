"""Tests for the SET_BUTTONS ZIP payload builder.

Ground truth for the manifest schema and frame-boundary firmware workaround
comes from redphx/strmdck (MIT).
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from ulanzi_linux.domain.button_config import ButtonConfig, TextStyle
from ulanzi_linux.infrastructure.zip_builder import (
    ICON_SIZE,
    build_buttons_zip,
)


@pytest.fixture
def fake_icon(tmp_path: Path) -> Path:
    """Produce a 200x200 RGBA PNG so we exercise the resize path."""
    path = tmp_path / "icon.png"
    Image.new("RGBA", (200, 200), (255, 0, 0, 255)).save(path, format="PNG")
    return path


def test_zip_contains_manifest_icons_and_dummy(fake_icon: Path) -> None:
    blob = build_buttons_zip(
        [ButtonConfig(index=0, icon_path=fake_icon, label="A")]
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "icons/0.png" in names
        assert "dummy.txt" in names


def test_manifest_uses_col_row_keys(fake_icon: Path) -> None:
    """D200 firmware expects ``{col}_{row}`` keys, not a flat array."""
    configs = [
        ButtonConfig(index=0, icon_path=fake_icon, label="A"),  # col=0 row=0
        ButtonConfig(index=5, icon_path=fake_icon, label="F"),  # col=0 row=1
        ButtonConfig(index=7, icon_path=fake_icon, label="H"),  # col=2 row=1
    ]
    blob = build_buttons_zip(configs)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert set(manifest.keys()) == {"0_0", "0_1", "2_1"}
    entry = manifest["0_0"]
    assert entry["State"] == 0
    assert entry["ViewParam"][0]["Text"] == "A"
    assert entry["ViewParam"][0]["Icon"] == "icons/0.png"


def test_icon_is_resized_to_expected_size(fake_icon: Path) -> None:
    blob = build_buttons_zip([ButtonConfig(index=0, icon_path=fake_icon)])
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        img = Image.open(io.BytesIO(zf.read("icons/0.png")))
        assert img.size == ICON_SIZE


def test_icon_size_is_native_196(fake_icon: Path) -> None:
    """Firmware expects native 196x196 icons (per strmdck)."""
    assert ICON_SIZE == (196, 196)


def test_boundary_bytes_avoid_invalid_markers(fake_icon: Path) -> None:
    """Every 1024-byte frame boundary must skip 0x00 and 0x7C."""
    configs = [
        ButtonConfig(index=i, icon_path=fake_icon, label=f"B{i}") for i in range(13)
    ]
    blob = build_buttons_zip(configs)
    for offset in range(1016, len(blob), 1024):
        assert blob[offset : offset + 1] not in (b"\x00", b"\x7c"), (
            f"invalid boundary byte at offset {offset}"
        )


def test_full_upload_fills_missing_buttons_with_black_tiles(fake_icon: Path) -> None:
    blob = build_buttons_zip(
        [ButtonConfig(index=0, icon_path=fake_icon, label="A")],
        fill_missing=True,
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        names = zf.namelist()
    assert len(manifest) == 13
    assert "icons/12.png" not in names
    assert manifest["1_0"]["ViewParam"] == [{}]


def test_label_only_button_renders_text_tile_and_manifest_text() -> None:
    blob = build_buttons_zip(
        [ButtonConfig(index=0, label="OpenAI")],
        fill_missing=True,
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        names = zf.namelist()
        img = Image.open(io.BytesIO(zf.read("icons/0.png")))
    assert "icons/0.png" in names
    assert manifest["0_0"]["ViewParam"][0]["Icon"] == "icons/0.png"
    assert manifest["0_0"]["ViewParam"][0]["Text"] == "OpenAI"
    assert img.size == ICON_SIZE


def test_text_only_button_uses_configured_background_color() -> None:
    blob = build_buttons_zip(
        [
            ButtonConfig(
                index=0,
                label="Hi",
                text_style=TextStyle(background_color="#AA1122"),
            )
        ]
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        img = Image.open(io.BytesIO(zf.read("icons/0.png"))).convert("RGBA")
    assert img.getpixel((4, 4)) == (170, 17, 34, 255)


def test_full_upload_preserves_last_physical_button(fake_icon: Path) -> None:
    blob = build_buttons_zip(
        [ButtonConfig(index=12, icon_path=fake_icon, label="Last")],
        fill_missing=True,
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        names = zf.namelist()
    assert "icons/12.png" in names
    assert manifest["2_2"]["ViewParam"][0]["Text"] == "Last"
    assert manifest["2_2"]["ViewParam"][0]["Icon"] == "icons/12.png"


def test_rejects_info_window_index_as_button(fake_icon: Path) -> None:
    with pytest.raises(ValueError, match="supported D200 grid"):
        build_buttons_zip([ButtonConfig(index=13, icon_path=fake_icon, label="Wide")])
