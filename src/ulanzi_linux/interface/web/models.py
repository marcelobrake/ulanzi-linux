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

from pydantic import BaseModel, Field


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
    "ConfigGetResponse",
    "ConfigPutRequest",
    "ConfigValidateRequest",
    "DeviceSummary",
    "HealthResponse",
    "PageSummary",
    "ValidationSummary",
]
