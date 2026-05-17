"""Host-side renderer for the D200 wide small-window strip."""

from __future__ import annotations

import io
import math
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

INFO_WINDOW_SIZE = (392, 196)
_DIGITAL_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSansMono-Bold.ttf",
    "DejaVuSans-Bold.ttf",
)
_LABEL_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans.ttf",
)


def _hex_to_rgba(value: str) -> tuple[int, int, int, int]:
    cleaned = value.lstrip("#")
    return (
        int(cleaned[0:2], 16),
        int(cleaned[2:4], 16),
        int(cleaned[4:6], 16),
        255,
    )


def _load_font(
    candidates: tuple[str, ...],
    *,
    size: int,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in candidates:
        if candidate.startswith("/") and not Path(candidate).exists():
            continue
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _parse_time(value: str) -> tuple[int, int, int]:
    try:
        parsed = datetime.strptime(value, "%H:%M:%S")
        return parsed.hour, parsed.minute, parsed.second
    except ValueError:
        return (0, 0, 0)


def _draw_clock_face(
    draw: ImageDraw.ImageDraw,
    *,
    center: tuple[float, float],
    radius: float,
    hour: int,
    minute: int,
    second: int,
) -> None:
    cx, cy = center
    outer_box = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw.ellipse(outer_box, fill=(11, 18, 32, 90), outline=(248, 250, 252, 255), width=4)
    inner_radius = radius - 10
    draw.ellipse(
        (cx - inner_radius, cy - inner_radius, cx + inner_radius, cy + inner_radius),
        outline=(148, 163, 184, 255),
        width=2,
    )

    for tick in range(60):
        angle = math.radians((tick * 6) - 90)
        outer = radius - 10
        inner = outer - (14 if tick % 5 == 0 else 7)
        start = (cx + math.cos(angle) * inner, cy + math.sin(angle) * inner)
        end = (cx + math.cos(angle) * outer, cy + math.sin(angle) * outer)
        draw.line((start, end), fill=(241, 245, 249, 255), width=3 if tick % 5 == 0 else 1)

    def _hand(angle_deg: float, length: float, width: int, fill: tuple[int, int, int, int]) -> None:
        angle = math.radians(angle_deg - 90)
        end = (cx + math.cos(angle) * length, cy + math.sin(angle) * length)
        draw.line(((cx, cy), end), fill=fill, width=width)

    hour_angle = ((hour % 12) + (minute / 60)) * 30
    minute_angle = (minute + (second / 60)) * 6
    second_angle = second * 6
    _hand(hour_angle, radius * 0.48, 6, (248, 250, 252, 255))
    _hand(minute_angle, radius * 0.7, 4, (191, 219, 254, 255))
    _hand(second_angle, radius * 0.78, 2, (248, 113, 113, 255))
    draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=(248, 250, 252, 255))


def render_small_window_clock_png(
    *,
    background_color: str,
    digital_time: str,
    analog_time: str,
) -> bytes:
    img = Image.new("RGBA", INFO_WINDOW_SIZE, _hex_to_rgba(background_color))
    draw = ImageDraw.Draw(img)

    hour, minute, second = _parse_time(analog_time)
    _draw_clock_face(
        draw,
        center=(98, 98),
        radius=72,
        hour=hour,
        minute=minute,
        second=second,
    )

    digital_font = _load_font(_DIGITAL_FONT_CANDIDATES, size=54)
    label_font = _load_font(_LABEL_FONT_CANDIDATES, size=20)
    accent = (191, 219, 254, 255)
    primary = (248, 250, 252, 255)
    secondary = (148, 163, 184, 255)
    draw.text((190, 42), "CLOCK", font=label_font, fill=accent)
    draw.text((190, 74), digital_time, font=digital_font, fill=primary)
    draw.text((190, 136), analog_time, font=label_font, fill=secondary)
    return _png_bytes(img)


def render_small_window_metrics_png(
    *,
    background_color: str,
    metric_lines: list[str],
) -> bytes:
    img = Image.new("RGBA", INFO_WINDOW_SIZE, _hex_to_rgba(background_color))
    draw = ImageDraw.Draw(img)

    title_font = _load_font(_LABEL_FONT_CANDIDATES, size=20)
    line_font = _load_font(_DIGITAL_FONT_CANDIDATES, size=34 if len(metric_lines) >= 3 else 40)
    draw.text((24, 18), "STATS", font=title_font, fill=(191, 219, 254, 255))
    top = 56 if len(metric_lines) >= 3 else 64
    spacing = 36 if len(metric_lines) >= 3 else 46
    for idx, line in enumerate(metric_lines):
        draw.text((24, top + (idx * spacing)), line, font=line_font, fill=(248, 250, 252, 255))
    return _png_bytes(img)
