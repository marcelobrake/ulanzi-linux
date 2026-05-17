# Changelog

<!-- markdownlint-disable MD024 -->

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.10.3] — 2026-05-17

### Fixed

- Custom `small_window.metrics_items` mode now pre-clears the firmware-native
  clock/stats cache with blank payloads before pinning the strip to
  `BACKGROUND`. On devices that still resurrect the old native layer, that
  fallback now returns blank instead of showing stale statistics underneath
  the host-rendered pages.

## [0.10.2] — 2026-05-17

### Fixed

- Custom `small_window.metrics_items` mode no longer mixes firmware-native
  `CLOCK` / `STATS` packets with the Linux-rendered strip. Both the clock
  page and the stats page are now rendered host-side while the device stays
  pinned to `BACKGROUND`, avoiding the stale `CPU/RAM/GPU` overlay that some
  D200 firmware builds kept reviving underneath the custom page.
- The custom clock page now draws an analog + digital layout in the wide
  strip, preserving the earlier visual style without relying on the unstable
  firmware-native clock transition path.

## [0.10.1] — 2026-05-17

### Fixed

- Custom `small_window.metrics_items` mode now keeps the native D200 clock
  during the clock phase of `rotate_every_s`, restoring the analog + digital
  clock presentation while still switching back to the Linux-rendered custom
  metrics page for the stats phase.
- The custom metrics phase now reasserts `BACKGROUND` immediately before every
  wide-strip render tick, reducing cases where the firmware-native
  `CPU/RAM/GPU` panel could bleed through underneath the custom page.

## [0.10.0] — 2026-05-17

### Added

- Added optional `small_window.metrics_items`, letting the editor and YAML
  select up to three custom Linux-host metrics for the wide status strip:
  `cpu`, `memory`, `gpu`, `temperature`, `disk`, `network`, and `battery`.
  Leaving the list empty preserves the firmware-native stats mode; selecting
  items switches the strip to a Linux-rendered custom page.

### Fixed

- The desktop window now passes the bundled Ulanzi icon into the Qt webview
  startup path, so the running app no longer falls back to the generic gear
  icon in the dock / task switcher.
- The visual editor small-window preview now mirrors the selected custom
  metrics and keeps the existing clock/stats rotation workflow for the new
  Linux-rendered mode.

- Restored the D200 small-window payload to the protocol used by the
  `redphx/strmdck` reference implementation: `STATS=0`, `CLOCK=1`, and live
  ASCII updates in the `mode|cpu|mem|time|gpu` format. This replaces the
  experimental native-mode packets that left some devices stuck on the static
  `CPU/RAM/GPU 0%` firmware screen.
- The desktop launcher now resolves and writes the absolute `ulanzi-linux`
  executable path into `Exec=` and `TryExec=` so GNOME can keep the app visible
  in the Applications menu even when the graphical session does not inherit the
  same `$PATH` as the terminal.
- `./systemd/install.sh` now installs the desktop editor launcher together with
  the user service and session-agent autostart entry, keeping the menu
  integration in sync with the active Python environment.
- The native desktop wrapper now avoids the optional tray thread unless
  explicitly requested and falls back to `QT_IM_MODULE=xim` when the host has
  exhausted its inotify watch budget, reducing Qt startup failures on busy
  GNOME desktops.

## [0.9.4] — 2026-05-17

### Fixed

- The daemon now keeps the D200 small window in `BACKGROUND` continuously and
  renders the alternating clock / CPU-MEM strip itself, so the firmware's
  native `CPU/RAM/GPU` panel no longer gets stuck underneath the custom view.
- CPU sampling for the rendered stats strip now stays warm even while the
  clock phase is active, avoiding alternation cycles that could show `CPU 0%`
  just because the stats phase had to re-prime `/proc/stat`.
- The visual editor now preserves the `info window` "Aparece em todas as
  páginas" choice when you save, even if that wide slot is being used only as
  the shared small-window touch area with no extra icon or label.

## [0.9.3] — 2026-05-17

### Fixed

- Restored native `SET_SMALL_WINDOW_DATA` updates for the D200 small window, so
  live clock and CPU/memory refreshes no longer sit on top of stale CPU/RAM/GPU
  artifacts left behind by the previous screen.
- Kept the configurable wide background strip upload in place while switching
  the live overlay back to the firmware-supported small-window protocol, which
  avoids the zeroed dynamic text layer that could appear after mode changes or
  reconnects.

## [0.9.2] — 2026-05-16

### Fixed

- The desktop editor now auto-selects `QT_QPA_PLATFORM=wayland` on Wayland
  sessions when the user has not set an explicit Qt platform, avoiding the
  fatal Qt `xcb` plugin crash seen on GNOME Wayland.
- The editor frontend now boots with a safe placeholder state, preventing the
  startup-time Alpine expression errors that could appear inside the desktop
  webview before the first `/api/editor` response arrived.

## [0.9.1] — 2026-05-16

### Fixed

- Stopped pinning `Pillow==11.1.0` inside the `desktop` extra, so installing
  `.[desktop]` no longer tries to downgrade and rebuild Pillow from source on
  hosts that already have a newer compatible wheel available.
- The `ulanzi-linux desktop` command now reports a clear install hint when a
  runtime desktop dependency such as `pywebview` is missing instead of dumping
  a raw Python traceback.

## [0.9.0] — 2026-05-16

### Added

- Added a Linux desktop application wrapper for the local editor using
  pywebview, with a user-scoped `desktop-install` command that writes the
  launcher and SVG icon into the standard Ubuntu desktop directories.
- Added built-in emoji assets to the editor catalog using local emoji
  metadata plus Noto Color Emoji rendering, so the same catalog now serves
  both application icons and emojis.

### Changed

- The built-in asset browser is now shared across web and desktop launches,
  and imported assets continue to land in `icons/builtin/` as regular PNGs
  for the existing deck upload pipeline.

## [0.8.0] — 2026-05-16

### Added

- Added a built-in icon catalog to the editor using Font Awesome Free,
  exposing more than 2000 searchable application/symbol icons that can be
  previewed in the UI and imported into the local icon directory for deck
  upload.

### Changed

- The web editor now imports selected built-in icons as local PNG files under
  `icons/builtin/`, so deck uploads keep working through the existing image
  pipeline.

## [0.7.0] — 2026-05-16

### Added

- Added `small_window.background_color` with web-editor support so the daemon
  uploads a solid wide background for the D200 small window, defaulting to
  black when the field is omitted.

### Changed

- The daemon now reapplies the small-window background as a dedicated partial
  update for the info strip, preserving the existing 13-button layout upload
  path while still restoring the background after reconnects.

## [0.6.0] — 2026-05-16

### Added

- Added compatibility support for `predefined_command` actions in YAML
  configs, including common desktop/media IDs such as `audio_mic_mute`,
  `display_screenshot_selection`, and `media_play_pause`.

### Fixed

- `ulanzi-linux daemon`, `push-config`, and the web editor validation flow
  now accept deck files that use `action.type: predefined_command`
  instead of failing with `unknown action type`.

## [0.5.0] — 2026-04-19

### Added

- Added optional `small_window.rotate_every_s` so the daemon can keep the
  D200 small window on the clock layout for a configured duration and then
  switch to the stats layout for the same duration, while still refreshing
  often enough to satisfy the firmware watchdog.

### Changed

- The web editor now exposes the small-window alternation interval and
  summarizes the alternating mode directly in the device preview.

## [0.4.1] — 2026-04-19

### Fixed

- `systemd/install.sh` now forces a real `systemctl --user restart`
  after installation so an already-running daemon reloads the current
  package code instead of keeping the previous Python module set in
  memory.

## [0.4.0] — 2026-04-19

### Added

- Added a graphical-session agent launched from desktop autostart that
  listens on a per-user Unix socket and executes shell, URL and shortcut
  actions from the active graphical login instead of relying exclusively
  on the systemd daemon process environment.

### Changed

- The daemon ActionRunner now attempts to delegate GUI-relevant actions
  to the session agent first and only falls back to the previous local
  execution strategy when the agent socket is unavailable.

### Fixed

- The systemd installer now also installs a desktop autostart entry for
  the graphical-session agent, so daemon-managed button actions can still
  open applications reliably after login on hosts where systemd's user
  environment is not enough by itself.

## [0.3.10] — 2026-04-19

### Fixed

- GUI shell commands that include extra flags now still recognize the
  underlying desktop app for window reuse, and if the raw command exits
  quickly without surfacing a window the daemon now tries the matching
  desktop launcher as an asynchronous fallback instead of stopping at the
  shell failure.
- Generated text-only button tiles now use content-specific icon names in
  the ZIP payload, which prevents stale labels from being reused by the
  firmware cache when two pages assign different text to the same button
  index.

## [0.3.9] — 2026-04-19

### Fixed

- URL actions now try the concrete `Exec=` command from the default
  browser desktop entry before falling back to generic desktop openers,
  which improves reliability on hosts where `gio open` does not surface a
  visible tab or window change.

## [0.3.8] — 2026-04-19

### Fixed

- The user-systemd installer now resolves the real `ulanzi-linux`
  executable from the active shell before writing `ExecStart=`, which
  prevents `status=203/EXEC` on hosts that install the package via pyenv
  or a virtual environment instead of `~/.local/bin`.

## [0.3.7] — 2026-04-19

### Fixed

- Simple GUI shell actions now try to focus an already-open matching
  window before launching a new instance, which makes app buttons behave
  correctly when the application is already running in the background.
- If a desktop launcher returns success but no matching window appears,
  the daemon now falls back to the raw shell command instead of assuming
  the app opened visibly.

## [0.3.6] — 2026-04-19

### Fixed

- After a successful GUI app launch through a desktop entry, the daemon
  now tries to activate the matching application window on X11 hosts that
  provide `wmctrl`, so buttons behave more like bringing an already-open
  app to the foreground.
- After handing a URL to the desktop opener, the daemon now also tries to
  focus the default browser window on X11 hosts with `wmctrl`, reducing
  the cases where the tab opens in the background with no visible change.

## [0.3.5] — 2026-04-19

### Fixed

- URL actions now prefer the desktop session opener path (`gio open`
  before the older fallbacks), which improves opening links in the active
  browser session and falls back to the default browser when needed.
- Simple GUI shell actions such as `code`, `claude-desktop`, and
  `chatgpt-desktop` now try the matching `.desktop` launcher
  (`gtk-launch` / `gio launch`) before spawning the raw binary, making
  app buttons behave more like clicking an application icon from the
  desktop environment.

## [0.3.4] — 2026-04-19

### Added

- Structured logs are now mirrored to the host syslog facility by default on
  POSIX systems, so daemon activity can be inspected outside the journal when
  operators prefer syslog-based troubleshooting.

### Changed

- Button handling now logs a fuller action lifecycle: physical button event,
  resolved action payload, dispatch acceptance, and per-action completion or
  failure details for shell, shortcut and URL actions.

## [0.3.3] — 2026-04-19

### Fixed

- Shell actions now log non-zero exit codes instead of failing silently in the
  background, which makes bad commands in `deck.yaml` diagnosable from daemon
  logs.

## [0.3.2] — 2026-04-19

### Changed

- Enlarged the visual deck simulator tiles in the localhost editor so the
  button grid is easier to inspect and click during layout work.
- Moved the simulator block to the top of the left column, immediately below
  the title area and above the summary cards, so the deck itself is visible
  first when opening the editor.

## [0.3.1] — 2026-04-19

### Changed

- Refreshed the localhost editor with a denser control-room layout: top summary
  cards, clearer helper panels, action-specific guidance, and a direct "test
  link" affordance for URL actions in the inspector.

### Fixed

- Shell and direct-exec actions now inherit a richer user-oriented environment:
  the daemon augments `$PATH` with the login-shell path when available plus the
  common Snap and Flatpak export directories, so apps installed outside the base
  distro path resolve more reliably.
- URL actions now normalize schemeless entries such as `claude.ai` to
  `https://claude.ai` before opening, and the editor applies the same
  normalization on blur/save so saved actions match runtime behavior.

## [0.3.0] — 2026-04-18

### Added

- Added a live small-window preview to the localhost editor so the wide
  bottom-right simulator tile now reflects the real device mode: clock or
  CPU/MEM stats, refreshed from the host in real time.
- Added automatic timestamped snapshots on every config save and an optional
  ZIP bundle export for the payload that would be sent to the deck. The same
  export path is also available from `ulanzi-linux push-config --save-firmware`.

### Changed

- Tightened the visual simulator to use fixed 96×96 button tiles and removed
  the extra simulator header panel to free vertical space in the editor.
- Image uploads are now normalized into 196×196 PNG assets with preserved
  aspect ratio and at least 5 px of breathing room on every side before they
  are previewed or packaged for the D200.

## [0.2.19] — 2026-04-18

### Changed

- Updated the public documentation to match the behavior now validated on the
  real D200: `show_metrics` switches between clock and stats layouts, icon
  uploads are fitted into 196×196 opaque PNG tiles, and real icon buttons do
  not rely on manifest text overlays.

### Removed

- Removed leftover local debugging artifacts and generated ZIP snapshots that
  were useful during reverse engineering but are not part of the project.

## [0.2.18] — 2026-04-18

### Fixed

- Changed uploaded icon assets to keep their original source basenames inside
  the `SET_BUTTONS` ZIP instead of always renaming them to numeric indices.
  The older D200 path preserved source names, and the real hardware still
  appears sensitive to that archive layout.
- Flattened uploaded PNG icons onto an opaque button-sized background before
  zipping them, instead of streaming transparent RGBA assets directly. This
  matches the more conservative rendering path used by generated text tiles
  and avoids firmware-side transparency quirks.

## [0.2.17] — 2026-04-18

### Fixed

- Stopped including `Text` in the `SET_BUTTONS` manifest for buttons that
  already have a real uploaded icon file. On the real D200, the firmware can
  prefer manifest text fallback over the PNG asset, which left icon-backed
  buttons rendering only their labels.

## [0.2.16] — 2026-04-18

### Fixed

- Reordered the `SET_BUTTONS` ZIP so `dummy.txt` once again sits before the
  icon files, matching the padding strategy that previously worked on the real
  D200. This keeps the firmware boundary workaround affecting the icon entries
  instead of only the archive tail.
- Added a separate final `sentinel.txt` entry so the firmware can still drop
  the last ZIP member without sacrificing a real icon asset.

## [0.2.15] — 2026-04-18

### Fixed

- Restored the small-window mode mapping that kept stats mode working on the
  real D200: `STATS=0` and `CLOCK=1`.
- Changed clock-mode updates to send zeroed metric slots (`1|0|0|HH:MM:SS|0`)
  instead of empty fields. The device was treating empty metric fields as the
  stats layout with `0%`, so disabling the stats option no longer falls back
  to fake zeroed stats.

## [0.2.14] — 2026-04-18

### Fixed

- Corrected the D200 small-window mode mapping again based on the current
  hardware behavior: `CLOCK=0` and `STATS=1`. The daemon was sending
  `mode_value=1` for clock mode, and the device kept rendering the stats
  layout with `0%` values instead of switching back to the clock.
- Updated the small-window regression tests and protocol notes to reflect the
  corrected clock payload wire format.

## [0.2.13] — 2026-04-18

### Fixed

- Restored time-bearing payloads in CLOCK mode. Version 0.2.12 kept the deck
  alive with the mode byte only, which left the real D200 without any clock
  text to render when `show_metrics` was disabled.
- Reconnect now replays cached CLOCK state with both the mode byte and the
  last time-only payload, so the small window comes back correctly after a
  transport reset.

## [0.2.12] — 2026-04-18

### Fixed

- Stopped sending telemetry payloads while the D200 is in clock mode. The real
  device was rendering `0%` stats whenever a clock-mode payload still carried
  metric slots, so clock mode now keeps itself alive with the mode byte only.
- Updated the web editor copy to match the observed firmware behavior: the
  toggle currently acts as a switch between exclusive clock and stats layouts,
  not a combined `clock + CPU/mem` overlay.

## [0.2.11] — 2026-04-18

### Fixed

- Combined the two small-window findings from the real device: keep sending a
  one-byte mode payload to flip layouts, but restore the pipe-separated data
  payload that was the last variant to produce real CPU/memory readings.
- Restored a final `dummy.txt` ZIP sentinel while keeping a separate
  `padding.bin` entry for boundary shifting. This preserves the 1024-byte
  workaround without risking the last physical button icon being treated as the
  final archive entry.

## [0.2.10] — 2026-04-18

### Fixed

- Restored the historical D200 small-window wire protocol: mode changes are
  again sent as a single-byte payload, while telemetry updates are sent as
  ASCII `cpu,mem,gpu[,time]`.
- Replaced the unified `mode|cpu|mem|time|gpu` payload after validating on the
  real device that it could surface stats but would not render the clock area
  correctly.

## [0.2.9] — 2026-04-18

### Fixed

- Restored the D200 small-window mode mapping to `STATS=0` and `CLOCK=1`
  after validating 0.2.8 against the real device: the hardware still rendered
  plain clock for wire mode `1` and stats-with-zeroes for wire mode `0` with
  empty metric fields.
- Kept the cached-mode fallback fix so mode `0` is no longer lost during the
  normal data update path or reconnect replay.

## [0.2.8] — 2026-04-18

### Fixed

- Fixed the D200 small-window mode mapping again based on the now-clean device
  behavior: `CLOCK=0` and `STATS=1`.
- Fixed cached small-window mode handling to avoid treating mode `0` as false
  during payload generation and reconnect replay. This restores the expected
  behavior where enabling stats shows CPU/memory values and disabling stats
  returns to the plain clock screen.

## [0.2.7] — 2026-04-18

### Fixed

- Fixed the SET_BUTTONS ZIP boundary workaround for layouts that combine a real
  uploaded icon with the bottom-row page buttons. The padding file now shifts
  the icon data that follows instead of being written too late to affect the
  failing 1024-byte boundaries.
- Added a regression test that reproduces the current `OpenAI + Media/Main/Dev`
  layout so this firmware workaround stays covered.

## [0.2.6] — 2026-04-18

### Fixed

- Fixed the D200 small-window mode mapping again after validating the cleaned
  runtime without the legacy daemon. The stats layout now uses the numeric mode
  that matches the device behavior observed on this host, which should restore
  CPU/memory display and the lower button row together.
- Added numeric mode values to small-window runtime logs so future hardware
  checks can verify the exact wire-mode being sent without ambiguity.

## [0.2.5] — 2026-04-18

### Fixed

- Fixed the small-window clock showing `00:00` on hardware that requires a
  full `HH:MM:SS` wire value even when the configured `time_format` is `%H:%M`.
  The daemon now keeps the user-facing short format but appends seconds on the
  wire for compact clock strings.

## [0.2.4] — 2026-04-18

### Fixed

- Fixed the small-window time payload regression that was forcing `HH:MM:SS`
  even when the configured format was shorter. The daemon now respects the
  configured `time_format`, which matches the documented `%H:%M` layout used
  for clock-plus-metrics on this project.
- Added more explicit runtime logging for small-window payloads and page-switch
  no-op presses to make on-device behavior diagnosable from local logs.

## [0.2.3] — 2026-04-18

### Fixed

- Fixed duplicated labels on text-rendered buttons by disabling the D200
  firmware title overlay while keeping the centered text tile generated by
  this project.

## [0.2.2] — 2026-04-18

### Fixed

- Fixed the D200 small-window mode enum values to match the behavior observed
  on the device used by this project, so `show_metrics: true` now sends the
  numeric mode that renders stats and `show_metrics: false` returns to the
  clock layout.

## [0.2.1] — 2026-04-18

### Fixed

- Fixed HID opening to probe the enumerated D200 paths explicitly instead of
  relying on `hid.open(vendor, product)`, which was unstable on hosts where
  only one of the exposed interfaces is actually openable.
- Fixed small-window mode selection so `show_metrics: true` drives the D200 in
  stats mode and `show_metrics: false` returns to the clock-only mode.
- Fixed text-only button manifests to include the `Text` field again alongside
  the generated icon tile, restoring button visibility for label-only buttons
  such as the current buttons `0`, `10`, `11` and `12`.

## [0.2.0] — 2026-04-18

### Added

- Added text-only button rendering with per-button `text_style` options,
  including background color, font color, bold, italic, underline, font
  family and font size. Text-only buttons are now rendered into the tile
  itself and stay centered both vertically and horizontally.
- Added visual editor controls for text-only button formatting, with live
  color pickers and a smaller deck preview that fits more comfortably
  without forcing unnecessary scrolling.

### Changed

- The info window touch area (index `13`) remains excluded from visual ZIP
  uploads, but is now supported end-to-end in the YAML/editor as an
  action-only slot.

### Fixed

- Fixed the small-window clock wire value to send a firmware-compatible
  `HH:MM:SS` payload again, preventing regressions where the D200 fell
  back to `00:00`.
- Fixed URL actions triggered by the user daemon to prefer desktop
  launchers such as `xdg-open` and `gio`, which are more reliable than
  the stdlib browser launcher in a systemd user service context.

## [0.1.5] — 2026-04-18

### Fixed

- Corrected the D200 layout model back to 13 physical buttons plus the
  separate wide info window. The web editor now reserves the lower-right
  wide slot for the small-window panel instead of treating it as a
  clickable button.
- Fixed full button uploads to emit empty `ViewParam` entries for blank
  buttons, matching the strmdck protocol shape and allowing resets to
  clear stale button content reliably.
- Normalized small-window clock updates to always send an `HH:MM:SS`
  compatible wire value to the device, even when the UI is configured to
  display only `HH:MM`.

## [0.1.4] — 2026-04-18

### Fixed

- Fixed full layout uploads to clear stale button labels by always sending
  an explicit empty `Text` field for blank buttons. This prevents old
  captions from surviving after a reset or a hot reload to an empty slot.
- Fixed the first `CLOCK` small-window update to avoid an empty mode packet,
  and restored `gpu=0` on metric payloads so the firmware receives the
  expected `mode|cpu|mem|time|gpu` shape during live refresh.

## [0.1.3] — 2026-04-18

### Fixed

- Fixed hot-reload uploads for the D200's last addressable button. Full
  uploads now include index `13`, so changes saved from the web editor or
  YAML watcher are no longer dropped for the bottom-right slot during
  layout sync.
- Corrected the documented D200 button index range to `0–13`.

## [0.1.2] — 2026-04-18

### Fixed

- Fixed the visual editor reset flow so `Reset` no longer auto-saves the
  cleared deck immediately. The layout now remains dirty until the user
  clicks `Salvar no deck`, keeping the primary save button enabled for
  explicit confirmation.

## [0.1.1] — 2026-04-18

### Added

- Added `AGENTS.md` as the repository-level operating guide for AI coding
  agents, documenting architecture, runtime model, source-of-truth files,
  common workflows and validation commands.
- Added compatibility guidance for AI-assisted tools that expect
  `AGENTS.md` or `CLAUDE.md` style repository instructions.

### Changed

- Established a mandatory release workflow for AI-driven changes:
  every accepted change must increment the project version and add a new
  top entry to `CHANGELOG.md`.
- Defined explicit bump rules for breaking changes, new features and
  compatible fixes so the AI can choose the correct version increment.

## [0.1.0] — 2026-04-18

First public release. End-to-end workflow works on real Ulanzi D200
hardware. 71 tests passing in CI.

### Added

- **Device enumeration** — `ulanzi-linux devices` lists attached D200
  units (VID `0x2207`, PID `0x0019`) via `hidapi`.
- **Button event stream** — `ulanzi-linux listen` decodes HID input
  reports and emits `ButtonEvent` / `DeviceInfoEvent` domain events.
- **LCD brightness control** — `ulanzi-linux brightness N` (0-100).
- **Icon + label upload** — `ulanzi-linux push-config deck.yaml` uploads
  layouts via the ZIP HID protocol (icons resized to 72×72 PNG).
- **Multi-page layouts** — named `pages:` plus `fixed_buttons:` rendered
  on every page. `switch_page` action for page navigation.
- **Daemon** — `ulanzi-linux daemon deck.yaml` runs the event loop,
  action runner (`shell` / `shortcut` / `url` / `switch_page`), small
  window refresher, and hot-reload watcher.
- **YAML hot-reload** — `ConfigWatcher` polls mtime every ~1 s; atomic
  in-memory swap on successful reparse. Bad YAML leaves the running
  config untouched.
- **Small window panel** — CPU / memory / date+time pushed at
  configurable cadence. Replaces the firmware heartbeat when enabled.
- **systemd user unit** — `systemd/ulanzi-linux.service` + `install.sh`.
  `Restart=on-failure`, graceful SIGTERM shutdown, JSON logs to
  journald, `loginctl enable-linger` for headless.
- **Localhost web editor** — `ulanzi-linux gui deck.yaml` on port 8765.
  FastAPI backend + CodeMirror 6 + Alpine.js frontend. Atomic file
  writes, validate-before-persist, decoupled from the daemon.
- **Observability** — `structlog`-based structured logging, JSON mode
  for production, OpenTelemetry hooks behind the `[telemetry]` extra.
- **Clean architecture layers** — `domain` / `application` /
  `infrastructure` / `interface` / `observability` with enforced
  dependency direction.
- **Documentation** — operations manual, configuration reference,
  systemd unit doc, web editor doc, architecture notes, protocol notes.

### Device support

- Ulanzi Stream Controller D200 (Rockchip RK3308HS, firmware-provided
  ZIP protocol for icon upload).

### Credits

Reverse-engineering stood on the shoulders of
[`redphx/strmdck`](https://github.com/redphx/strmdck) and
[`redphx/homedeck`](https://github.com/redphx/homedeck). The official
[`UlanziDeckPlugin-SDK`](https://github.com/UlanziTechnology/UlanziDeckPlugin-SDK)
was used to cross-check manifest and icon sizing.

[0.1.5]: https://github.com/marcelobrake/ulanzi-linux/releases/tag/v0.1.5
[0.1.4]: https://github.com/marcelobrake/ulanzi-linux/releases/tag/v0.1.4
[0.1.3]: https://github.com/marcelobrake/ulanzi-linux/releases/tag/v0.1.3
[0.1.2]: https://github.com/marcelobrake/ulanzi-linux/releases/tag/v0.1.2
[0.1.1]: https://github.com/marcelobrake/ulanzi-linux/releases/tag/v0.1.1
[0.1.0]: https://github.com/marcelobrake/ulanzi-linux/releases/tag/v0.1.0
