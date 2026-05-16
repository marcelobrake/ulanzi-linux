"""Built-in icon catalog backed by Font Awesome Free webfonts."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ICON_RENDER_SIZE = (256, 256)
ICON_FOREGROUND = "#F8FAFC"

_STYLE_TO_FONT = {
    "solid": "fa-solid-900.ttf",
    "regular": "fa-regular-400.ttf",
    "brands": "fa-brands-400.ttf",
}


@dataclass(frozen=True, slots=True)
class BuiltinIcon:
    asset_id: str
    name: str
    style: str
    unicode_hex: str
    search_terms: tuple[str, ...]


def _fontawesome_root() -> Path:
    import fontawesomefree

    return Path(fontawesomefree.__file__).resolve().parent / "static" / "fontawesomefree"


def _hex_to_rgba(value: str, *, alpha: int = 255) -> tuple[int, int, int, int]:
    cleaned = value.strip().lstrip("#")
    return (
        int(cleaned[0:2], 16),
        int(cleaned[2:4], 16),
        int(cleaned[4:6], 16),
        alpha,
    )


@lru_cache(maxsize=1)
def _fontawesome_metadata() -> dict[str, dict[str, object]]:
    metadata_path = _fontawesome_root() / "metadata" / "icons.json"
    return json.loads(metadata_path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def list_builtin_icons() -> tuple[BuiltinIcon, ...]:
    icons: list[BuiltinIcon] = []
    for name, payload in _fontawesome_metadata().items():
        unicode_hex = str(payload["unicode"])
        raw_styles = payload.get("styles") or []
        search = payload.get("search") or {}
        search_terms = set(search.get("terms") or [])
        aliases = payload.get("aliases") or {}
        search_terms.update(aliases.get("names") or [])
        search_terms.add(name)
        search_terms.update(name.split("-"))
        for style in raw_styles:
            if style not in _STYLE_TO_FONT:
                continue
            icons.append(
                BuiltinIcon(
                    asset_id=f"fa:{style}:{name}",
                    name=name,
                    style=str(style),
                    unicode_hex=unicode_hex,
                    search_terms=tuple(sorted(str(term) for term in search_terms)),
                )
            )
    icons.sort(key=lambda icon: (icon.style, icon.name))
    return tuple(icons)


@lru_cache(maxsize=4096)
def get_builtin_icon(asset_id: str) -> BuiltinIcon:
    for icon in list_builtin_icons():
        if icon.asset_id == asset_id:
            return icon
    raise KeyError(asset_id)


@lru_cache(maxsize=8)
def _font_path(style: str) -> str:
    return str(_fontawesome_root() / "webfonts" / _STYLE_TO_FONT[style])


def _fit_icon_font_size(
    glyph: str,
    *,
    font_path: str,
    canvas_size: tuple[int, int],
    padding: int,
) -> ImageFont.FreeTypeFont:
    scratch = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(scratch)
    max_width = canvas_size[0] - (padding * 2)
    max_height = canvas_size[1] - (padding * 2)
    for size in range(min(canvas_size) - padding, 24, -4):
        font = ImageFont.truetype(font_path, size=size)
        box = draw.textbbox((0, 0), glyph, font=font)
        width = box[2] - box[0]
        height = box[3] - box[1]
        if width <= max_width and height <= max_height:
            return font
    return ImageFont.truetype(font_path, size=24)


@lru_cache(maxsize=4096)
def render_builtin_icon_png(
    asset_id: str,
    *,
    size: tuple[int, int] = ICON_RENDER_SIZE,
    foreground: str = ICON_FOREGROUND,
    background: str | None = None,
) -> bytes:
    icon = get_builtin_icon(asset_id)
    glyph = chr(int(icon.unicode_hex, 16))
    image = Image.new(
        "RGBA",
        size,
        (0, 0, 0, 0) if background is None else _hex_to_rgba(background),
    )
    draw = ImageDraw.Draw(image)
    font = _fit_icon_font_size(
        glyph,
        font_path=_font_path(icon.style),
        canvas_size=size,
        padding=max(12, size[0] // 10),
    )
    box = draw.textbbox((0, 0), glyph, font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    x = (size[0] - width) / 2 - box[0]
    y = (size[1] - height) / 2 - box[1]
    draw.text((x, y), glyph, font=font, fill=_hex_to_rgba(foreground))

    buffer = Path
    del buffer
    from io import BytesIO

    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def materialize_builtin_icon(asset_id: str, target_dir: Path) -> Path:
    icon = get_builtin_icon(asset_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"fontawesome-{icon.style}-{icon.name}.png"
    if not target.exists():
        target.write_bytes(render_builtin_icon_png(asset_id))
    return target


__all__ = [
    "BuiltinIcon",
    "get_builtin_icon",
    "list_builtin_icons",
    "materialize_builtin_icon",
    "render_builtin_icon_png",
]