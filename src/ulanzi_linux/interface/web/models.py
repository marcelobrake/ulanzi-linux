"""Pydantic request/response models for the web UI API.

We keep these separate from the domain dataclasses (``ButtonConfig``,
``DeckConfig``) because:
    * pydantic v2 has its own validation semantics that can drift from
      our ``__post_init__`` invariants — we don't want two sources of
      truth.
    * the API speaks raw YAML text, not structured JSON objects, so the
      models here are thin.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ulanzi_linux.domain.button_config import (
    DEFAULT_TEXT_BACKGROUND_COLOR,
    DEFAULT_TEXT_COLOR,
    DEFAULT_TEXT_FONT_FAMILY,
    DEFAULT_TEXT_FONT_SIZE,
    DEFAULT_TIME_FORMAT,
)


class ConfigGetResponse(BaseModel):
    """Current state of the YAML file on disk."""

    path: str = Field(..., description="Absolute path to the deck.yaml file.")
    content: str = Field(..., description="Raw YAML text as read from disk.")
    mtime: float = Field(
        ..., description="File modification time as a POSIX timestamp."
    )
    size: int = Field(..., description="File size in bytes.")


class ConfigPutRequest(BaseModel):
    """YAML payload the user wants to persist."""

    content: str = Field(..., description="Raw YAML text to write to disk.")


class ConfigValidateRequest(BaseModel):
    """Validate-only request — never touches disk."""

    content: str = Field(..., description="Raw YAML text to run through the loader.")


class PageSummary(BaseModel):
    """Parsed summary of a single page — fed to the UI sidebar."""

    name: str
    button_count: int
    indices: list[int]


class ValidationSummary(BaseModel):
    """Result of running ``load_deck_config`` on YAML text."""

    ok: bool
    error: str | None = None
    default_page: str | None = None
    pages: list[PageSummary] = Field(default_factory=list)
    fixed_button_indices: list[int] = Field(default_factory=list)
    small_window_enabled: bool = False


class EditorActionModel(BaseModel):
    """Structured action payload used by the visual editor."""

    type: Literal["none", "shell", "shortcut", "url", "switch_page"] = "none"
    cmd: str = ""
    keys: str = ""
    url: str = ""
    page: str = ""


class EditorTextStyleModel(BaseModel):
    """Visual options for text-only buttons."""

    background_color: str = DEFAULT_TEXT_BACKGROUND_COLOR
    text_color: str = DEFAULT_TEXT_COLOR
    bold: bool = False
    italic: bool = False
    underline: bool = False
    font_family: str = DEFAULT_TEXT_FONT_FAMILY
    font_size: int = DEFAULT_TEXT_FONT_SIZE


class EditorButtonModel(BaseModel):
    """Visual editor representation of a single button."""

    index: int
    label: str = ""
    icon_path: str | None = None
    preview_url: str | None = None
    action: EditorActionModel = Field(default_factory=EditorActionModel)
    text_style: EditorTextStyleModel = Field(default_factory=EditorTextStyleModel)


class EditorPageModel(BaseModel):
    """Named page used by the visual editor."""

    name: str
    buttons: list[EditorButtonModel] = Field(default_factory=list)


class EditorSmallWindowModel(BaseModel):
    """Small-window config surfaced in the visual editor."""

    enabled: bool = False
    interval_s: float = 2.0
    time_format: str = DEFAULT_TIME_FORMAT
    show_metrics: bool = True


class EditorConfigResponse(BaseModel):
    """Full structured config consumed by the visual editor."""

    path: str
    config_exists: bool
    default_page: str
    pages: list[EditorPageModel] = Field(default_factory=list)
    fixed_buttons: list[EditorButtonModel] = Field(default_factory=list)
    small_window: EditorSmallWindowModel = Field(
        default_factory=EditorSmallWindowModel
    )


class EditorConfigPutRequest(BaseModel):
    """Structured config the visual editor wants to persist."""

    default_page: str
    pages: list[EditorPageModel] = Field(default_factory=list)
    fixed_buttons: list[EditorButtonModel] = Field(default_factory=list)
    small_window: EditorSmallWindowModel = Field(
        default_factory=EditorSmallWindowModel
    )


class AssetUploadResponse(BaseModel):
    """Metadata for an uploaded icon asset."""

    path: str
    preview_url: str


class DeviceSummary(BaseModel):
    """Enumerated D200 device info."""

    manufacturer: str | None = None
    product: str | None = None
    serial: str | None = None
    interface_number: int | None = None
    path: str | None = None


class HealthResponse(BaseModel):
    """Quick liveness + environment probe used by the UI header."""

    ok: bool = True
    version: str
    config_path: str
    config_exists: bool
    devices_found: int


__all__ = [
    "AssetUploadResponse",
    "ConfigGetResponse",
    "ConfigPutRequest",
    "ConfigValidateRequest",
    "DeviceSummary",
    "EditorActionModel",
    "EditorButtonModel",
    "EditorConfigPutRequest",
    "EditorConfigResponse",
    "EditorPageModel",
    "EditorSmallWindowModel",
    "EditorTextStyleModel",
    "HealthResponse",
    "PageSummary",
    "ValidationSummary",
]
