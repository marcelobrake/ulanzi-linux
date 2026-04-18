"""Load a DeckConfig from a YAML file.

Two schemas are accepted:

Multi-page (preferred):
    default_page: main
    pages:
      main:
        buttons:
          - index: 0
            icon: ~/.config/ulanzi/icons/term.png
            label: Terminal
            action: { type: shell, cmd: "gnome-terminal" }
      media:
        buttons: [...]
    fixed_buttons:
      - index: 10
        label: Main
        action: { type: switch_page, page: main }

Legacy single-page:
    buttons:
      - index: 0
        ...

The legacy form is normalised into a single ``default`` page so the
downstream code only sees the multi-page shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from ulanzi_linux.domain.button_config import (
    DEFAULT_PAGE_NAME,
    DEFAULT_TIME_FORMAT,
    Action,
    ButtonConfig,
    DeckConfig,
    Page,
    ShellAction,
    ShortcutAction,
    SmallWindowConfig,
    SwitchPageAction,
    UrlAction,
)

logger = structlog.get_logger(__name__)


def _parse_action(raw: dict[str, Any] | None) -> Action | None:
    if raw is None:
        return None
    kind = raw.get("type")
    if kind == "shell":
        return ShellAction(type="shell", cmd=str(raw["cmd"]))
    if kind == "shortcut":
        return ShortcutAction(type="shortcut", keys=str(raw["keys"]))
    if kind == "url":
        return UrlAction(type="url", url=str(raw["url"]))
    if kind == "switch_page":
        return SwitchPageAction(type="switch_page", page=str(raw["page"]))
    raise ValueError(f"unknown action type: {kind!r}")


def _parse_button(raw: dict[str, Any]) -> ButtonConfig:
    icon_raw = raw.get("icon")
    icon_path = Path(str(icon_raw)).expanduser() if icon_raw else None
    return ButtonConfig(
        index=int(raw["index"]),
        icon_path=icon_path,
        label=str(raw.get("label", "")),
        action=_parse_action(raw.get("action")),
    )


def _parse_buttons(raws: list[dict[str, Any]] | None) -> tuple[ButtonConfig, ...]:
    return tuple(_parse_button(r) for r in (raws or []))


def _parse_small_window(raw: dict[str, Any] | None) -> SmallWindowConfig:
    """Parse the ``small_window:`` YAML block (all keys optional)."""
    if not raw:
        return SmallWindowConfig()
    return SmallWindowConfig(
        enabled=bool(raw.get("enabled", False)),
        interval_s=float(raw.get("interval_s", 2.0)),
        time_format=str(raw.get("time_format", DEFAULT_TIME_FORMAT)),
    )


def load_deck_config(path: str | Path) -> DeckConfig:
    """Parse a YAML file into a DeckConfig.

    Supports both legacy (flat ``buttons:``) and multi-page
    (``pages: {name: {buttons: [...]}}``) schemas.
    """
    text = Path(path).expanduser().read_text(encoding="utf-8")
    doc = yaml.safe_load(text) or {}

    small_window = _parse_small_window(doc.get("small_window"))

    if "pages" in doc:
        raw_pages: dict[str, Any] = doc["pages"] or {}
        if not raw_pages:
            raise ValueError("'pages:' block is empty")
        pages = {
            name: Page(name=name, buttons=_parse_buttons(spec.get("buttons")))
            for name, spec in raw_pages.items()
        }
        fixed = _parse_buttons(doc.get("fixed_buttons"))
        default_page = str(doc.get("default_page") or next(iter(pages)))
        logger.info(
            "config_loaded",
            schema="multi_page",
            pages=list(pages.keys()),
            fixed_buttons=len(fixed),
            default_page=default_page,
            small_window_enabled=small_window.enabled,
        )
        return DeckConfig(
            pages=pages,
            fixed_buttons=fixed,
            default_page=default_page,
            small_window=small_window,
        )

    # Legacy single-page: wrap the flat ``buttons:`` list into one page.
    buttons = _parse_buttons(doc.get("buttons"))
    logger.info(
        "config_loaded",
        schema="single_page_legacy",
        buttons=len(buttons),
        small_window_enabled=small_window.enabled,
    )
    # single_page() helper doesn't know about small_window; rebuild by hand.
    return DeckConfig(
        pages={DEFAULT_PAGE_NAME: Page(name=DEFAULT_PAGE_NAME, buttons=buttons)},
        default_page=DEFAULT_PAGE_NAME,
        small_window=small_window,
    )


__all__ = ["load_deck_config"]
