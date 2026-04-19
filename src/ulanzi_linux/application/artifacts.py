"""Helpers for versioned config snapshots and deck upload bundles."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ulanzi_linux.domain.button_config import DeckConfig
from ulanzi_linux.infrastructure.zip_builder import build_buttons_zip

TIMESTAMP_TOKEN_FORMAT = "%Y%m%d-%H%M%S"


def timestamp_token(now: datetime | None = None) -> str:
    """Return a filesystem-safe timestamp token for saved artifacts."""
    return (now or datetime.now()).strftime(TIMESTAMP_TOKEN_FORMAT)


def versioned_output_path(
    path: Path,
    *,
    token: str,
    label: str | None = None,
    extension: str | None = None,
) -> Path:
    """Return a unique sibling path carrying ``token`` as a filename suffix."""
    suffix = extension if extension is not None else path.suffix
    name_parts = [path.stem]
    if label:
        name_parts.append(label)
    name_parts.append(token)
    candidate = path.with_name(f"{'-'.join(name_parts)}{suffix}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(
            f"{'-'.join(name_parts)}-{counter:02d}{suffix}"
        )
        counter += 1
    return candidate


def build_default_page_bundle(cfg: DeckConfig, *, partial: bool = False) -> bytes:
    """Build the ZIP payload that would be uploaded for the default page."""
    layout = cfg.buttons_for(cfg.default_page)
    return build_buttons_zip(layout, fill_missing=not partial)


__all__ = [
    "TIMESTAMP_TOKEN_FORMAT",
    "build_default_page_bundle",
    "timestamp_token",
    "versioned_output_path",
]
