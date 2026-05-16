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
    DEFAULT_SMALL_WINDOW_BACKGROUND_COLOR,
    DEFAULT_TEXT_BACKGROUND_COLOR,
    DEFAULT_TEXT_COLOR,
    DEFAULT_TEXT_FONT_FAMILY,
    DEFAULT_TEXT_FONT_SIZE,
    DEFAULT_TIME_FORMAT,
    Action,
    ButtonConfig,
    DeckConfig,
    Page,
    PredefinedCommandAction,
    ShellAction,
    ShortcutAction,
    SmallWindowConfig,
    SwitchPageAction,
    TextStyle,
    UrlAction,
)

logger = structlog.get_logger(__name__)

RENDERABLE_BUTTON_INDICES = frozenset(range(13))
SUPPORTED_BUTTON_INDICES = frozenset(range(14))
INFO_WINDOW_INDEX = 13


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
    if kind == "predefined_command":
        return PredefinedCommandAction(
            type="predefined_command",
            command_id=str(raw["command_id"]),
        )
    raise ValueError(f"unknown action type: {kind!r}")


def _parse_button(raw: dict[str, Any]) -> ButtonConfig:
    icon_raw = raw.get("icon")
    icon_path = Path(str(icon_raw)).expanduser() if icon_raw else None
    text_style_raw = raw.get("text_style") or {}
    return ButtonConfig(
        index=int(raw["index"]),
        icon_path=icon_path,
        label=str(raw.get("label", "")),
        action=_parse_action(raw.get("action")),
        text_style=TextStyle(
            background_color=str(
                text_style_raw.get(
                    "background_color",
                    DEFAULT_TEXT_BACKGROUND_COLOR,
                )
            ),
            text_color=str(
                text_style_raw.get(
                    "text_color",
                    DEFAULT_TEXT_COLOR,
                )
            ),
            bold=bool(text_style_raw.get("bold", False)),
            italic=bool(text_style_raw.get("italic", False)),
            underline=bool(text_style_raw.get("underline", False)),
            font_family=str(
                text_style_raw.get(
                    "font_family",
                    DEFAULT_TEXT_FONT_FAMILY,
                )
            ),
            font_size=int(
                text_style_raw.get(
                    "font_size",
                    DEFAULT_TEXT_FONT_SIZE,
                )
            ),
        ),
    )


def _parse_buttons(
    raws: list[dict[str, Any]] | None,
    *,
    scope: str,
) -> tuple[ButtonConfig, ...]:
    buttons: list[ButtonConfig] = []
    for raw in raws or []:
        button = _parse_button(raw)
        if button.index not in SUPPORTED_BUTTON_INDICES:
            logger.warning(
                "unsupported_button_ignored",
                scope=scope,
                index=button.index,
                supported_range="0..13",
                reason="out_of_range",
            )
            continue
        if button.index == INFO_WINDOW_INDEX and (
            button.label or button.icon_path is not None
        ):
            logger.warning(
                "info_window_visual_ignored",
                scope=scope,
                index=button.index,
            )
        buttons.append(button)
    return tuple(buttons)


def _parse_small_window(raw: dict[str, Any] | None) -> SmallWindowConfig:
    """Parse the ``small_window:`` YAML block (all keys optional)."""
    if not raw:
        return SmallWindowConfig()
    rotate_every_raw = raw.get("rotate_every_s")
    return SmallWindowConfig(
        enabled=bool(raw.get("enabled", False)),
        interval_s=float(raw.get("interval_s", 2.0)),
        time_format=str(raw.get("time_format", DEFAULT_TIME_FORMAT)),
        show_metrics=bool(raw.get("show_metrics", True)),
        rotate_every_s=(
            None
            if rotate_every_raw in (None, "")
            else float(rotate_every_raw)
        ),
        background_color=str(
            raw.get(
                "background_color",
                DEFAULT_SMALL_WINDOW_BACKGROUND_COLOR,
            )
        ),
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
            name: Page(
                name=name,
                buttons=_parse_buttons(
                    spec.get("buttons"),
                    scope=f"page:{name}",
                ),
            )
            for name, spec in raw_pages.items()
        }
        fixed = _parse_buttons(doc.get("fixed_buttons"), scope="fixed_buttons")
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
    buttons = _parse_buttons(doc.get("buttons"), scope="buttons")
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
