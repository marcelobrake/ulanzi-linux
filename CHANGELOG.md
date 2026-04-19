# Changelog

<!-- markdownlint-disable MD024 -->

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
