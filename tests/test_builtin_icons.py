from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

pytest.importorskip("fontawesomefree")

from ulanzi_linux.infrastructure.builtin_icons import (
    list_builtin_icons,
    materialize_builtin_icon,
    render_builtin_icon_png,
)


def test_builtin_catalog_exposes_more_than_one_thousand_icons() -> None:
    icons = list_builtin_icons()
    assert len(icons) > 1000


def test_builtin_icon_can_render_to_png() -> None:
    icon = list_builtin_icons()[0]
    payload = render_builtin_icon_png(icon.asset_id)

    with Image.open(io.BytesIO(payload)) as image:
        assert image.size == (256, 256)
        assert image.getchannel("A").getextrema()[1] > 0


def test_materialize_builtin_icon_writes_png_file(tmp_path: Path) -> None:
    icon = list_builtin_icons()[0]
    target = materialize_builtin_icon(icon.asset_id, tmp_path)

    assert target.exists()
    assert target.suffix == ".png"