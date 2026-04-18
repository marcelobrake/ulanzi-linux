"""Domain model for button configuration, pages and actions.

``ButtonConfig`` describes what a single button looks like and what it does
when pressed. ``Page`` groups buttons that share the top-area grid, and
``DeckConfig`` holds the whole deck layout: named pages, a default page,
and an optional list of ``fixed_buttons`` rendered on every page (typically
the physical bottom row used as page switchers).

Actions are a discriminated union so new types can be added without
touching the core dispatch logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


# ---------------------------------------------------------------------- #
# Actions                                                                #
# ---------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ShellAction:
    """Run an arbitrary shell command."""

    type: Literal["shell"]
    cmd: str


@dataclass(frozen=True, slots=True)
class ShortcutAction:
    """Emit a keyboard shortcut, e.g. ``ctrl+alt+t``."""

    type: Literal["shortcut"]
    keys: str


@dataclass(frozen=True, slots=True)
class UrlAction:
    """Open a URL in the default browser."""

    type: Literal["url"]
    url: str


@dataclass(frozen=True, slots=True)
class SwitchPageAction:
    """Switch the daemon's active page.

    The daemon intercepts this action before invoking the runner; it is a
    pure domain concern so it cannot touch ``subprocess`` or the host.
    """

    type: Literal["switch_page"]
    page: str


Action = ShellAction | ShortcutAction | UrlAction | SwitchPageAction


# ---------------------------------------------------------------------- #
# Buttons and pages                                                      #
# ---------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ButtonConfig:
    """A single button's visuals + behaviour."""

    index: int
    icon_path: Path | None = None
    label: str = ""
    action: Action | None = None


@dataclass(frozen=True, slots=True)
class Page:
    """A named layout — buttons shown when this page is active."""

    name: str
    buttons: tuple[ButtonConfig, ...] = field(default_factory=tuple)

    def by_index(self, idx: int) -> ButtonConfig | None:
        for b in self.buttons:
            if b.index == idx:
                return b
        return None


DEFAULT_PAGE_NAME = "default"


# Default date/time format: day/month hour:minute (pt-BR friendly, compact
# enough to fit the D200 small-window area).
DEFAULT_TIME_FORMAT = "%d/%m %H:%M"

# Max guardrail for the small-window refresh interval — the device
# watchdog fires ~5s; anything slower risks falling back to standalone
# mode. The lower bound only exists to prevent a busy-loop (0.0 would
# mean "push as fast as possible" and blow the USB bus).
SMALL_WINDOW_MIN_INTERVAL_S = 0.05
SMALL_WINDOW_MAX_INTERVAL_S = 4.5


@dataclass(frozen=True, slots=True)
class SmallWindowConfig:
    """Small-window (left status panel) refresh configuration.

    When ``enabled``, the daemon takes over the small window with CPU,
    memory and date/time — and *replaces* the plain heartbeat loop,
    because the heartbeat already uses ``SET_SMALL_WINDOW_DATA`` under
    the hood and would otherwise overwrite real stats with zeros.
    """

    enabled: bool = False
    interval_s: float = 2.0
    time_format: str = DEFAULT_TIME_FORMAT

    def __post_init__(self) -> None:
        if not (
            SMALL_WINDOW_MIN_INTERVAL_S
            <= self.interval_s
            <= SMALL_WINDOW_MAX_INTERVAL_S
        ):
            raise ValueError(
                f"small_window.interval_s={self.interval_s} out of range "
                f"[{SMALL_WINDOW_MIN_INTERVAL_S}, "
                f"{SMALL_WINDOW_MAX_INTERVAL_S}]"
            )


@dataclass(frozen=True, slots=True)
class DeckConfig:
    """Full deck configuration loaded from YAML.

    A config always has at least one page. Single-page configs (legacy YAML
    with a flat ``buttons:`` key) are normalised to a one-entry ``pages``
    dict named ``default`` so downstream code never special-cases them.
    """

    pages: dict[str, Page] = field(default_factory=dict)
    fixed_buttons: tuple[ButtonConfig, ...] = field(default_factory=tuple)
    default_page: str = DEFAULT_PAGE_NAME
    small_window: SmallWindowConfig = field(default_factory=SmallWindowConfig)

    def __post_init__(self) -> None:
        if not self.pages:
            raise ValueError("DeckConfig requires at least one page")
        if self.default_page not in self.pages:
            raise ValueError(
                f"default_page {self.default_page!r} is not in pages "
                f"({sorted(self.pages)!r})"
            )
        # Fixed buttons and page buttons must not collide on index, or the
        # last write wins silently and drives the operator mad.
        fixed_idx = {b.index for b in self.fixed_buttons}
        for page in self.pages.values():
            clash = fixed_idx.intersection(b.index for b in page.buttons)
            if clash:
                raise ValueError(
                    f"page {page.name!r} reuses fixed_button indices "
                    f"{sorted(clash)!r}"
                )

    def page(self, name: str) -> Page:
        try:
            return self.pages[name]
        except KeyError as exc:
            raise KeyError(
                f"page {name!r} not defined; known: {sorted(self.pages)!r}"
            ) from exc

    def buttons_for(self, name: str) -> tuple[ButtonConfig, ...]:
        """Return the on-screen layout for ``name`` — page + fixed buttons."""
        return self.page(name).buttons + self.fixed_buttons

    def button_at(self, page_name: str, index: int) -> ButtonConfig | None:
        """Resolve a button by page + physical index (fixed first)."""
        for b in self.fixed_buttons:
            if b.index == index:
                return b
        return self.page(page_name).by_index(index)

    # ------------------------------------------------------------------ #
    # Legacy single-page compatibility                                   #
    # ------------------------------------------------------------------ #

    @classmethod
    def single_page(
        cls, buttons: tuple[ButtonConfig, ...], name: str = DEFAULT_PAGE_NAME
    ) -> DeckConfig:
        """Build a config with one page named ``name`` (legacy shortcut)."""
        return cls(
            pages={name: Page(name=name, buttons=buttons)},
            default_page=name,
        )


__all__ = [
    "Action",
    "ButtonConfig",
    "DEFAULT_PAGE_NAME",
    "DEFAULT_TIME_FORMAT",
    "DeckConfig",
    "Page",
    "ShellAction",
    "ShortcutAction",
    "SMALL_WINDOW_MAX_INTERVAL_S",
    "SMALL_WINDOW_MIN_INTERVAL_S",
    "SmallWindowConfig",
    "SwitchPageAction",
    "UrlAction",
]
