"""Build the ZIP payload that SET_BUTTONS expects.

Schema (ground truth extracted from redphx/strmdck):
    manifest.json      JSON keyed by ``"{col}_{row}"`` (not flat array!)
                       Each entry: ``{"State": 0, "ViewParam": [{"Text", "Icon"}]}``
    icons/<name>.png   196x196 RGBA PNG per button
    dummy.txt          random padding file — exists solely to shift ZIP byte
                       offsets, see firmware-bug note below.

Firmware bug worked around here:
    The D200 firmware parses the ZIP while it's being streamed over HID in
    1024-byte frames. If the byte at offsets 1016, 2040, 3064, ... (i.e.
    the last byte of every 1024-byte boundary past the first header) equals
    0x00 or 0x7C (the packet magic), the firmware corrupts the upload and
    silently drops buttons or locks the deck. We regenerate ``dummy.txt``
    with progressively longer random content until the resulting ZIP passes
    the offset check.
"""

from __future__ import annotations

import colorsys
import io
import json
import secrets
import string
import zipfile
from collections.abc import Iterable

import structlog
from PIL import Image, ImageDraw, ImageFont

from ulanzi_linux.domain.button_config import ButtonConfig

logger = structlog.get_logger(__name__)

# Native icon resolution the D200 firmware expects.
ICON_SIZE = (196, 196)

# D200 grid geometry — used to derive ``col`` / ``row`` from a flat index.
# Kept local to the builder because the manifest schema is deck-specific.
_D200_COLS = 5

# Frame boundaries we must inspect for the firmware parser bug.
_FRAME_SIZE = 1024
_FIRST_CHECK_OFFSET = 1016  # last byte of first 1024-byte window, accounting for header
_INVALID_BOUNDARY_BYTES = (b"\x00", b"\x7c")
_MAX_DUMMY_RETRIES = 64


def _random_ascii(length: int) -> str:
    """Generate a printable ASCII string of ``length`` characters."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _placeholder_icon(index: int, label: str) -> bytes:
    """Render a fallback icon with the label centered on a coloured tile."""
    hue = (index * 0.137) % 1.0  # golden-angle spread for distinct colours
    r, g, b = (int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.55, 0.85))
    img = Image.new("RGBA", ICON_SIZE, (r, g, b, 255))
    draw = ImageDraw.Draw(img)
    text = (label or str(index))[:8]
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42
        )
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((ICON_SIZE[0] - tw) // 2, (ICON_SIZE[1] - th) // 2 - 4),
        text,
        fill=(255, 255, 255, 255),
        font=font,
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _normalize_icon(cfg: ButtonConfig) -> bytes:
    """Load and resize a PNG — or render a placeholder if file is missing."""
    from pathlib import Path

    path = Path(cfg.icon_path).expanduser() if cfg.icon_path else None
    if path is None or not path.exists():
        logger.warning(
            "icon_missing_using_placeholder",
            index=cfg.index,
            path=str(path) if path else None,
            label=cfg.label,
        )
        return _placeholder_icon(cfg.index, cfg.label)

    with Image.open(path) as img:
        img = img.convert("RGBA")
        if img.size != ICON_SIZE:
            img = img.resize(ICON_SIZE, Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def _build_manifest(configs: list[ButtonConfig]) -> dict:
    """Produce the manifest in the strmdck-compatible ``{col}_{row}`` schema."""
    manifest: dict = {}
    for cfg in configs:
        idx = int(cfg.index)
        row = idx // _D200_COLS
        col = idx % _D200_COLS
        view_param: dict = {}
        if cfg.label:
            view_param["Text"] = cfg.label
        # Icon filename uses the flat index for uniqueness, referenced from manifest.
        view_param["Icon"] = f"icons/{idx}.png"
        manifest[f"{col}_{row}"] = {
            "State": 0,
            "ViewParam": [view_param],
        }
    return manifest


def _assemble_zip(
    configs: list[ButtonConfig],
    icons: dict[int, bytes],
    manifest: dict,
    dummy_content: str,
) -> bytes:
    """Serialize the ZIP in canonical order (manifest, icons, dummy last)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        zf.writestr(
            "manifest.json",
            json.dumps(manifest, sort_keys=True, separators=(",", ":"), indent=2),
        )
        for cfg in configs:
            zf.writestr(f"icons/{int(cfg.index)}.png", icons[int(cfg.index)])
        # dummy.txt must exist so regeneration can shift boundary offsets.
        zf.writestr("dummy.txt", dummy_content)
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


def build_buttons_zip(configs: Iterable[ButtonConfig]) -> bytes:
    """Serialize a list of button configs into the on-wire ZIP blob.

    Automatically regenerates ``dummy.txt`` with random padding when the
    resulting ZIP would trip the D200 firmware's frame-boundary parser bug.
    """
    configs_list = list(configs)
    # Cache rendered icons so the retry loop doesn't re-encode PNGs.
    icons = {int(c.index): _normalize_icon(c) for c in configs_list}
    manifest = _build_manifest(configs_list)

    dummy = ""
    blob = _assemble_zip(configs_list, icons, manifest, dummy)
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
        # Grow the dummy file proportionally to the retry count — longer
        # strings shift more bytes and are more likely to land on a safe
        # boundary layout.
        dummy += _random_ascii(8 * retries)
        blob = _assemble_zip(configs_list, icons, manifest, dummy)
        logger.debug(
            "zip_boundary_retry",
            retries=retries,
            dummy_len=len(dummy),
            size=len(blob),
        )

    logger.info(
        "buttons_zip_built",
        buttons=len(configs_list),
        size=len(blob),
        dummy_retries=retries,
    )
    return blob


__all__ = ["ICON_SIZE", "build_buttons_zip"]
