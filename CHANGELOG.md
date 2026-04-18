# Changelog

<!-- markdownlint-disable MD024 -->

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.2]: https://github.com/marcelobrake/ulanzi-linux/releases/tag/v0.1.2
[0.1.1]: https://github.com/marcelobrake/ulanzi-linux/releases/tag/v0.1.1
[0.1.0]: https://github.com/marcelobrake/ulanzi-linux/releases/tag/v0.1.0
