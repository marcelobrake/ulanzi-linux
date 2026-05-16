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


@pytest.fixture
def noisy_icon(tmp_path: Path) -> Path:
    """Produce a deterministic high-entropy PNG closer to real uploaded assets."""
    path = tmp_path / "noisy.png"
    img = Image.new("RGBA", ICON_SIZE)
    pixels = img.load()
    for y in range(ICON_SIZE[1]):
        for x in range(ICON_SIZE[0]):
            pixels[x, y] = (
                (x * 37 + y * 17) % 256,
                (x * 13 + y * 29) % 256,
                (x * 73 + y * 7) % 256,
                255,
            )
    img.save(path, format="PNG", compress_level=0)
    return path


def test_zip_contains_manifest_icons_and_dummy(fake_icon: Path) -> None:
    blob = build_buttons_zip(
        [ButtonConfig(index=0, icon_path=fake_icon, label="A")]
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "icons/icon.png" in names
        assert "dummy.txt" in names
        assert "sentinel.txt" in names
        assert names[-1] == "sentinel.txt"
        assert names.index("dummy.txt") < names.index("icons/icon.png")


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
    assert entry["ViewParam"][0]["Icon"] == "icons/icon.png"
    assert "Text" not in entry["ViewParam"][0]


def test_icon_is_resized_to_expected_size(fake_icon: Path) -> None:
    blob = build_buttons_zip([ButtonConfig(index=0, icon_path=fake_icon)])
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        img = Image.open(io.BytesIO(zf.read("icons/icon.png")))
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


def test_boundary_workaround_handles_real_icon_plus_bottom_row(
    noisy_icon: Path,
) -> None:
    blob = build_buttons_zip(
        [
            ButtonConfig(index=0, icon_path=noisy_icon, label="OpenAI"),
            ButtonConfig(index=10, label="Media", text_style=TextStyle(font_size=48)),
            ButtonConfig(index=11, label="Main", text_style=TextStyle(font_size=48)),
            ButtonConfig(index=12, label="Dev", text_style=TextStyle(font_size=48)),
        ],
        fill_missing=True,
    )
    for offset in range(1016, len(blob), 1024):
        assert blob[offset : offset + 1] not in (b"\x00", b"\x7c"), (
            f"invalid boundary byte at offset {offset}"
        )
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        names = zf.namelist()
    assert names[-1] == "sentinel.txt"
    assert names.index("dummy.txt") < names.index("icons/noisy.png")
    assert manifest["0_2"]["ViewParam"][0]["Text"] == "Media"
    assert manifest["1_2"]["ViewParam"][0]["Text"] == "Main"
    assert manifest["2_2"]["ViewParam"][0]["Text"] == "Dev"


def test_full_upload_keeps_dummy_as_last_entry_for_final_icon(fake_icon: Path) -> None:
    blob = build_buttons_zip(
        [ButtonConfig(index=12, icon_path=fake_icon, label="Last")],
        fill_missing=True,
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
    assert "icons/icon.png" in names
    assert names[-1] == "sentinel.txt"


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


def test_label_only_button_uses_manifest_text_without_generated_icon() -> None:
    blob = build_buttons_zip(
        [ButtonConfig(index=0, label="OpenAI")],
        fill_missing=True,
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        names = zf.namelist()
    assert manifest["0_0"]["ViewParam"][0] == {"Text": "OpenAI"}
    assert all(not name.startswith("icons/0-") for name in names)


def test_label_only_button_text_changes_manifest_content() -> None:
    first_blob = build_buttons_zip([ButtonConfig(index=0, label="Main")])
    second_blob = build_buttons_zip([ButtonConfig(index=0, label="Media")])

    with zipfile.ZipFile(io.BytesIO(first_blob)) as first_zip:
        first_manifest = json.loads(first_zip.read("manifest.json"))
    with zipfile.ZipFile(io.BytesIO(second_blob)) as second_zip:
        second_manifest = json.loads(second_zip.read("manifest.json"))

    assert first_manifest["0_0"]["ViewParam"][0]["Text"] == "Main"
    assert second_manifest["0_0"]["ViewParam"][0]["Text"] == "Media"


def test_real_icon_keeps_original_basename_in_manifest(fake_icon: Path) -> None:
    blob = build_buttons_zip([ButtonConfig(index=10, icon_path=fake_icon, label="Media")])
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["0_2"]["ViewParam"][0] == {"Icon": "icons/icon.png"}


def test_real_icon_is_flattened_onto_opaque_button_background(tmp_path: Path) -> None:
    icon_path = tmp_path / "transparent.png"
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    pixels = img.load()
    for y in range(16, 48):
        for x in range(16, 48):
            pixels[x, y] = (255, 255, 255, 255)
    img.save(icon_path, format="PNG")

    blob = build_buttons_zip(
        [
            ButtonConfig(
                index=0,
                icon_path=icon_path,
                text_style=TextStyle(background_color="#112233"),
            )
        ]
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        rendered = Image.open(io.BytesIO(zf.read("icons/transparent.png"))).convert("RGBA")

    assert rendered.getpixel((4, 4)) == (17, 34, 51, 255)


def test_text_only_button_does_not_emit_generated_icon() -> None:
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
        manifest = json.loads(zf.read("manifest.json"))
        names = zf.namelist()
    assert manifest["0_0"]["ViewParam"][0] == {"Text": "Hi"}
    assert all(not name.startswith("icons/0-") for name in names)


def test_missing_icon_with_label_falls_back_to_manifest_text() -> None:
    blob = build_buttons_zip(
        [
            ButtonConfig(
                index=0,
                label="Term",
                icon_path=Path("/definitely/missing/icon.png"),
            )
        ]
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        names = zf.namelist()

    assert manifest["0_0"]["ViewParam"][0] == {"Text": "Term"}
    assert all(not name.startswith("icons/0-") for name in names)


def test_full_upload_preserves_last_physical_button(fake_icon: Path) -> None:
    blob = build_buttons_zip(
        [ButtonConfig(index=12, icon_path=fake_icon, label="Last")],
        fill_missing=True,
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        names = zf.namelist()
    assert "icons/icon.png" in names
    assert manifest["2_2"]["ViewParam"][0]["Icon"] == "icons/icon.png"
    assert "Text" not in manifest["2_2"]["ViewParam"][0]
    assert names[-1] == "sentinel.txt"


def test_icon_button_omits_manifest_text_to_force_png_render(fake_icon: Path) -> None:
    blob = build_buttons_zip([ButtonConfig(index=10, icon_path=fake_icon, label="Media")])
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["0_2"]["ViewParam"][0] == {"Icon": "icons/icon.png"}


def test_rejects_info_window_index_as_button(fake_icon: Path) -> None:
    with pytest.raises(ValueError, match="supported D200 grid"):
        build_buttons_zip([ButtonConfig(index=13, icon_path=fake_icon, label="Wide")])
