"""Build the ZIP payload that SET_BUTTONS expects.

Schema (ground truth extracted from redphx/strmdck):
    manifest.json      JSON keyed by ``"{col}_{row}"`` (not flat array!)
                       Each entry: ``{"State": 0, "ViewParam": [{...}]}``.
                       Label-only buttons carry ``Text`` plus a generated PNG;
                       icon-backed buttons carry only ``Icon`` so the firmware
                       prefers the uploaded asset over manifest text fallback.
    dummy.txt          stored padding file written before icons so retries can
                       shift subsequent ZIP entry offsets safely.
    icons/<name>.png   196x196 PNG assets. Real icons keep their source
                       basename, while generated text tiles use a stable
                       content hash so page switches cannot reuse stale
                       cached assets for the same physical index.
    sentinel.txt       empty final file so the firmware can discard the last
                       central-directory entry without losing a real icon.

Firmware bug worked around here:
    The D200 firmware parses the ZIP while it's being streamed over HID in
    1024-byte frames. If the byte at offsets 1016, 2040, 3064, ... (i.e.
    the last byte of every 1024-byte boundary past the first header) equals
    0x00 or 0x7C (the packet magic), the firmware corrupts the upload and
    silently drops buttons or locks the deck. We regenerate ``dummy.txt``
    with progressively longer stored padding until the resulting ZIP passes
    the offset check.
"""

from __future__ import annotations

import io
import json
import hashlib
import zipfile
from collections.abc import Iterable
from pathlib import Path

import structlog
from PIL import Image, ImageDraw, ImageFont, ImageOps

from ulanzi_linux.domain.button_config import ButtonConfig, TextStyle

logger = structlog.get_logger(__name__)

# Native icon resolution the D200 firmware expects.
ICON_SIZE = (196, 196)
INFO_WINDOW_SIZE = (ICON_SIZE[0] * 2, ICON_SIZE[1])

# D200 grid geometry — 13 physical buttons on the 5x3 grid. The wide
# bottom-right info window is controlled separately via small-window packets.
# Kept local to the builder because the manifest schema is deck-specific.
_D200_COLS = 5
_D200_ACTIVE_BUTTON_COUNT = 13
_D200_SUPPORTED_SLOT_COUNT = 14
_INFO_WINDOW_INDEX = 13

# Frame boundaries we must inspect for the firmware parser bug.
_FRAME_SIZE = 1024
_FIRST_CHECK_OFFSET = 1016  # last byte of first 1024-byte window, accounting for header
_INVALID_BOUNDARY_BYTES = (b"\x00", b"\x7c")
_MAX_DUMMY_RETRIES = 1024
_REAL_ICON_PADDING = 5
_TEXT_TILE_PADDING = 16
_TEXT_TILE_MAX_WIDTH = ICON_SIZE[0] - (_TEXT_TILE_PADDING * 2)
_TEXT_TILE_MAX_HEIGHT = ICON_SIZE[1] - (_TEXT_TILE_PADDING * 2)

_FONT_FILE_CANDIDATES: dict[str, dict[tuple[bool, bool], tuple[str, ...]]] = {
    "DejaVu Sans": {
        (False, False): (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "DejaVuSans.ttf",
        ),
        (True, False): (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "DejaVuSans-Bold.ttf",
        ),
        (False, True): (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
            "DejaVuSans-Oblique.ttf",
        ),
        (True, True): (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
            "DejaVuSans-BoldOblique.ttf",
        ),
    },
    "DejaVu Serif": {
        (False, False): (
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "DejaVuSerif.ttf",
        ),
        (True, False): (
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "DejaVuSerif-Bold.ttf",
        ),
        (False, True): (
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
            "DejaVuSerif-Italic.ttf",
        ),
        (True, True): (
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf",
            "DejaVuSerif-BoldItalic.ttf",
        ),
    },
    "DejaVu Sans Mono": {
        (False, False): (
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "DejaVuSansMono.ttf",
        ),
        (True, False): (
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
            "DejaVuSansMono-Bold.ttf",
        ),
        (False, True): (
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Oblique.ttf",
            "DejaVuSansMono-Oblique.ttf",
        ),
        (True, True): (
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-BoldOblique.ttf",
            "DejaVuSansMono-BoldOblique.ttf",
        ),
    },
    "Liberation Sans": {
        (False, False): (
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "LiberationSans-Regular.ttf",
        ),
        (True, False): (
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "LiberationSans-Bold.ttf",
        ),
        (False, True): (
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Italic.ttf",
            "LiberationSans-Italic.ttf",
        ),
        (True, True): (
            "/usr/share/fonts/truetype/liberation2/LiberationSans-BoldItalic.ttf",
            "LiberationSans-BoldItalic.ttf",
        ),
    },
    "Liberation Serif": {
        (False, False): (
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
            "LiberationSerif-Regular.ttf",
        ),
        (True, False): (
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf",
            "LiberationSerif-Bold.ttf",
        ),
        (False, True): (
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-Italic.ttf",
            "LiberationSerif-Italic.ttf",
        ),
        (True, True): (
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-BoldItalic.ttf",
            "LiberationSerif-BoldItalic.ttf",
        ),
    },
}
def _blank_icon() -> bytes:
    """Render a black tile used for unconfigured or cleared buttons."""
    img = Image.new("RGBA", ICON_SIZE, (0, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _render_info_window_background(background_color: str) -> bytes:
    img = Image.new("RGBA", INFO_WINDOW_SIZE, _hex_to_rgba(background_color))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _real_icon_path(cfg: ButtonConfig) -> Path | None:
    path = Path(cfg.icon_path).expanduser() if cfg.icon_path else None
    if path is None or not path.exists():
        return None
    return path


def _hex_to_rgba(value: str) -> tuple[int, int, int, int]:
    cleaned = value.lstrip("#")
    return (
        int(cleaned[0:2], 16),
        int(cleaned[2:4], 16),
        int(cleaned[4:6], 16),
        255,
    )


def _font_candidates(style: TextStyle) -> tuple[str, ...]:
    family = _FONT_FILE_CANDIDATES.get(
        style.font_family,
        _FONT_FILE_CANDIDATES["DejaVu Sans"],
    )
    return family[(style.bold, style.italic)]


def _load_font(style: TextStyle, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in _font_candidates(style):
        if candidate.startswith("/") and not Path(candidate).exists():
            continue
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(
    text: str,
    *,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    words = text.split()
    if not words:
        return [text]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if width <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
    lines.append(current)
    return lines


def _fit_text_layout(
    text: str,
    style: TextStyle,
) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, list[str], int]:
    scratch = Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(scratch)
    for size in range(style.font_size, 11, -2):
        font = _load_font(style, size)
        lines = _wrap_text(text, draw=draw, font=font, max_width=_TEXT_TILE_MAX_WIDTH)
        boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
        widths = [box[2] - box[0] for box in boxes]
        line_heights = [box[3] - box[1] for box in boxes]
        max_width = max(widths, default=0)
        spacing = max(6, size // 6)
        total_height = sum(line_heights) + spacing * max(0, len(lines) - 1)
        if max_width <= _TEXT_TILE_MAX_WIDTH and total_height <= _TEXT_TILE_MAX_HEIGHT:
            return font, lines, spacing
    font = _load_font(style, 12)
    lines = _wrap_text(text, draw=draw, font=font, max_width=_TEXT_TILE_MAX_WIDTH)
    return font, lines, 4


def _render_text_icon(cfg: ButtonConfig) -> bytes:
    style = cfg.text_style
    img = Image.new("RGBA", ICON_SIZE, _hex_to_rgba(style.background_color))
    draw = ImageDraw.Draw(img)
    font, lines, spacing = _fit_text_layout(cfg.label, style)
    boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    heights = [box[3] - box[1] for box in boxes]
    total_height = sum(heights) + spacing * max(0, len(lines) - 1)
    current_y = (ICON_SIZE[1] - total_height) / 2
    fill = _hex_to_rgba(style.text_color)

    for line, box, height in zip(lines, boxes, heights, strict=False):
        width = box[2] - box[0]
        x = (ICON_SIZE[0] - width) / 2
        y = current_y - box[1]
        draw.text((x, y), line, font=font, fill=fill)
        if style.underline:
            underline_y = current_y + height + 2
            draw.line(
                (
                    x,
                    underline_y,
                    x + width,
                    underline_y,
                ),
                fill=fill,
                width=max(1, style.font_size // 18),
            )
        current_y += height + spacing

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _normalize_icon(cfg: ButtonConfig) -> bytes:
    """Load and resize a PNG — or render a black tile if absent."""
    path = _real_icon_path(cfg)
    if int(cfg.index) == _INFO_WINDOW_INDEX:
        if path is None:
            return _render_info_window_background(cfg.text_style.background_color)
        with Image.open(path) as img:
            img = img.convert("RGBA")
            fitted = ImageOps.contain(
                img,
                INFO_WINDOW_SIZE,
                Image.Resampling.LANCZOS,
            )
            tile = Image.new(
                "RGBA",
                INFO_WINDOW_SIZE,
                _hex_to_rgba(cfg.text_style.background_color),
            )
            origin = (
                (INFO_WINDOW_SIZE[0] - fitted.width) // 2,
                (INFO_WINDOW_SIZE[1] - fitted.height) // 2,
            )
            tile.alpha_composite(fitted, origin)
            buf = io.BytesIO()
            tile.save(buf, format="PNG")
            return buf.getvalue()
    if path is None:
        if cfg.label:
            if cfg.icon_path is not None:
                logger.warning(
                    "button_icon_missing_falling_back_to_text",
                    index=int(cfg.index),
                    icon_path=str(Path(cfg.icon_path).expanduser()),
                )
            return _render_text_icon(cfg)
        return _blank_icon()

    with Image.open(path) as img:
        img = img.convert("RGBA")
        fitted = ImageOps.contain(
            img,
            (
                ICON_SIZE[0] - (_REAL_ICON_PADDING * 2),
                ICON_SIZE[1] - (_REAL_ICON_PADDING * 2),
            ),
            Image.Resampling.LANCZOS,
        )
        tile = Image.new("RGBA", ICON_SIZE, _hex_to_rgba(cfg.text_style.background_color))
        origin = (
            (ICON_SIZE[0] - fitted.width) // 2,
            (ICON_SIZE[1] - fitted.height) // 2,
        )
        tile.alpha_composite(fitted, origin)
        buf = io.BytesIO()
        tile.save(buf, format="PNG")
        return buf.getvalue()


def _has_real_icon(cfg: ButtonConfig) -> bool:
    return _real_icon_path(cfg) is not None


def _archive_icon_name(cfg: ButtonConfig) -> str:
    path = _real_icon_path(cfg)
    if path is not None:
        return f"icons/{path.name}"
    style = cfg.text_style
    payload = json.dumps(
        {
            "index": int(cfg.index),
            "label": cfg.label,
            "background_color": style.background_color,
            "text_color": style.text_color,
            "bold": style.bold,
            "italic": style.italic,
            "underline": style.underline,
            "font_family": style.font_family,
            "font_size": style.font_size,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    if int(cfg.index) == _INFO_WINDOW_INDEX:
        return f"icons/info-window-{digest}.png"
    return f"icons/{int(cfg.index)}-{digest}.png"


def _needs_icon_asset(cfg: ButtonConfig) -> bool:
    return int(cfg.index) == _INFO_WINDOW_INDEX or _has_real_icon(cfg)


def _build_manifest(configs: list[ButtonConfig]) -> dict:
    """Produce the manifest in the strmdck-compatible ``{col}_{row}`` schema."""
    manifest: dict = {}
    for cfg in configs:
        idx = int(cfg.index)
        row = idx // _D200_COLS
        col = idx % _D200_COLS
        view_param: dict = {}
        if idx == _INFO_WINDOW_INDEX:
            view_param["Icon"] = _archive_icon_name(cfg)
            manifest[f"{col}_{row}"] = {
                "State": 0,
                "ViewParam": [view_param],
            }
            continue
        has_real_icon = _has_real_icon(cfg)
        if cfg.label and not has_real_icon:
            view_param["Text"] = cfg.label
        if has_real_icon:
            view_param["Icon"] = _archive_icon_name(cfg)
        manifest[f"{col}_{row}"] = {
            "State": 0,
            "ViewParam": [view_param],
        }
    return manifest


def _validate_indices(configs: list[ButtonConfig]) -> None:
    for cfg in configs:
        idx = int(cfg.index)
        if not 0 <= idx < _D200_SUPPORTED_SLOT_COUNT:
            raise ValueError(
                "button index "
                f"{idx} is outside the supported D200 grid (0..{_D200_SUPPORTED_SLOT_COUNT - 1})"
            )


def _filled_button_layout(configs: list[ButtonConfig]) -> list[ButtonConfig]:
    by_index = {int(cfg.index): cfg for cfg in configs}
    return [
        by_index.get(index, ButtonConfig(index=index))
        for index in range(_D200_ACTIVE_BUTTON_COUNT)
    ]


def _assemble_zip(
    configs: list[ButtonConfig],
    icons: dict[str, bytes],
    manifest: dict,
    padding_len: int,
) -> bytes:
    """Serialize the ZIP in canonical order.

    ``dummy.txt`` is intentionally written before the icon entries so changing
    its size shifts all subsequent icon bytes and the final central directory.
    ``sentinel.txt`` remains the last file because the firmware has
    historically been sensitive to the final archive entry.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        zf.writestr(
            "manifest.json",
            json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        )
        dummy_info = zipfile.ZipInfo("dummy.txt")
        dummy_info.compress_type = zipfile.ZIP_STORED
        zf.writestr(dummy_info, b"A" * padding_len)
        for name, data in icons.items():
            zf.writestr(name, data)
        sentinel_info = zipfile.ZipInfo("sentinel.txt")
        sentinel_info.compress_type = zipfile.ZIP_STORED
        zf.writestr(sentinel_info, b"")
    return buf.getvalue()


def _boundary_bytes_are_safe(blob: bytes) -> bool:
    """Return True when no 1024-byte frame boundary ends on an invalid byte.

    The firmware mis-parses the stream if the byte right before a frame
    boundary is 0x00 (null) or 0x7C (the '|' magic byte).
    """
    size = len(blob)
    for offset in range(_FIRST_CHECK_OFFSET, size, _FRAME_SIZE):
        byte = blob[offset : offset + 1]
        if byte in _INVALID_BOUNDARY_BYTES:
            return False
    return True


def build_buttons_zip(
    configs: Iterable[ButtonConfig], *, fill_missing: bool = False
) -> bytes:
    """Serialize a list of button configs into the on-wire ZIP blob.

    Automatically regenerates ``dummy.txt`` with random padding when the
    resulting ZIP would trip the D200 firmware's frame-boundary parser bug.
    """
    configs_list = list(configs)
    _validate_indices(configs_list)
    if fill_missing:
        configs_list = _filled_button_layout(configs_list)
    # Cache rendered icons so the retry loop doesn't re-encode PNGs.
    icons: dict[str, bytes] = {}
    for cfg in configs_list:
        if not _needs_icon_asset(cfg):
            continue
        archive_name = _archive_icon_name(cfg)
        icons.setdefault(archive_name, _normalize_icon(cfg))
    manifest = _build_manifest(configs_list)

    padding_len = 0
    blob = _assemble_zip(configs_list, icons, manifest, padding_len)
    retries = 0
    while not _boundary_bytes_are_safe(blob):
        retries += 1
        if retries > _MAX_DUMMY_RETRIES:
            logger.error(
                "zip_boundary_retries_exhausted",
                retries=retries,
                size=len(blob),
            )
            raise RuntimeError(
                "Unable to produce a ZIP whose 1024-byte boundaries avoid "
                f"firmware invalid bytes after {retries} retries."
            )
        # Increase dummy.txt by one stored byte per retry so every subsequent
        # entry shifts deterministically through the 1024-byte boundaries,
        # while sentinel.txt stays last as a throwaway archive entry.
        padding_len = retries
        blob = _assemble_zip(configs_list, icons, manifest, padding_len)
        logger.debug(
            "zip_boundary_retry",
            retries=retries,
            dummy_len=padding_len,
            size=len(blob),
        )

    logger.info(
        "buttons_zip_built",
        buttons=len(configs_list),
        size=len(blob),
        dummy_retries=retries,
    )
    return blob


__all__ = ["ICON_SIZE", "INFO_WINDOW_SIZE", "build_buttons_zip"]
