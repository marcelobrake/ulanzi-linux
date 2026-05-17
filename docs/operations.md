# ulanzi-linux — Operations manual

End-to-end guide for running the Ulanzi Stream Controller D200 on Linux.
This document is aimed at the person who will install, operate and
troubleshoot the software on real hardware. For field-specific detail
refer to the companion docs:

- [`configuration.md`](configuration.md) — every YAML knob explained.
- [`systemd.md`](systemd.md) — unit file internals, service policies.
- [`web-ui.md`](web-ui.md) — the localhost editor and HTTP API.
- [`architecture.md`](architecture.md) — layer boundaries and why.
- [`protocol.md`](protocol.md) — HID packet shape and quirks.

## 1. Runtime model at a glance

```text
┌────────────────┐     writes       ┌─────────────────┐
│  Web editor    │ ───── deck.yaml ──▶│  ~/.config/ulanzi │
│  (optional)    │                  │     /deck.yaml    │
└────────────────┘                  └──────┬──────────┘
                                           │ polled ~1 s
                                           ▼
                              ┌─────────────────────────┐
                              │  Daemon (DeckDaemon)    │
                              │   - event loop          │
                              │   - small-window loop   │
                              │   - action runner       │
                              └──────┬──────────────────┘
                                     │ HID over USB
                                     ▼
                              ┌─────────────────────────┐
                              │  Ulanzi D200 hardware   │
                              └─────────────────────────┘
```

The editor and the daemon are independent processes. They share only the
YAML file on disk; neither talks to the other over IPC. This is the
reason the editor is safe to run while the daemon is live — no USB lock
contention, no stale protocol state.

## 2. Host requirements

| Item | Minimum | Notes |
| --- | --- | --- |
| Linux kernel | 5.10+ | Tested on 6.x; older kernels missing `hidraw` will not work. |
| Python | 3.11 | Type hints and `asyncio.TaskGroup` used throughout. |
| `libhidapi` | 0.14+ | Install: `sudo apt install libhidapi-hidraw0` (Debian/Ubuntu). Fedora: `sudo dnf install hidapi`. |
| udev | default | Needed to grant hidraw access without sudo — shipped in `udev/99-ulanzi-d200.rules`. |
| Membership in `plugdev` | required | `sudo usermod -aG plugdev "$USER"` → log out / in. |
| Free TCP port (editor only) | `8765` | Used by both `ulanzi-linux gui` and the desktop wrapper. Bound to loopback by default. |
| `fonts-noto-color-emoji` | optional | Enables local emoji previews/imports in the built-in asset catalog. |

The D200 enumerates as `2207:0019` (Rockchip vendor, Ulanzi product).
`ulanzi-linux devices` is the fastest way to confirm the OS sees it.

## 3. First-time install

```bash
# 3.1 — Clone and install the package.
git clone https://github.com/marcelobrake/ulanzi-linux.git
cd ulanzi-linux

python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,desktop]"   # full editor stack
# or: pip install -e ".[dev,web]" # browser-only editor

# 3.2 — Grant hidraw access to your user.
sudo cp udev/99-ulanzi-d200.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG plugdev "$USER"    # log out / in (or newgrp plugdev)

# 3.3 — Unplug and replug the deck so udev reapplies the rule.
ulanzi-linux devices

# 3.4 — Drop a starter config.
mkdir -p ~/.config/ulanzi
cp examples/deck.multipage.yaml ~/.config/ulanzi/deck.yaml

# 3.5 — First push + manual run.
ulanzi-linux push-config ~/.config/ulanzi/deck.yaml
ulanzi-linux daemon ~/.config/ulanzi/deck.yaml
```

At this point the deck shows your layout, button presses run the
configured actions, and `Ctrl-C` cleanly terminates the daemon. If any
of the above fails, jump to §10 Troubleshooting.

### 3.6 — System install (no venv)

If you'd rather keep things global:

```bash
pip install --user ".[web]"
# entry point lands at ~/.local/bin/ulanzi-linux
# make sure ~/.local/bin is on $PATH
```

The systemd unit shipped in this repo assumes exactly this location.

If you also want the installable desktop window and launcher integration,
use `pip install --user ".[desktop]"` instead.

## 4. Running the daemon

```bash
ulanzi-linux daemon <CONFIG_PATH> [--skip-sync] [--no-watch]
ulanzi-linux push-config <CONFIG_PATH> [--partial] [--save-firmware]
```

| Flag | Effect | When to use |
| --- | --- | --- |
| `--skip-sync` | Do not upload the layout at startup. | After an external `push-config`, to skip a redundant upload. |
| `--no-watch` | Disable the YAML hot-reload watcher. | Debugging. Production should keep hot-reload on. |

### Lifecycle

1. **Startup** — validate YAML, open HID device, sync layout, spawn the
   event listener, start the small-window loop (if enabled), start the
   `ConfigWatcher` (if `--no-watch` not passed).
2. **Runtime** — button events are converted into `ButtonEvent`
  messages; the action runner executes the bound action; the small-window
  loop pushes either the plain clock layout or the CPU/MEM stats layout
  every `interval_s` seconds depending on `small_window.show_metrics`; if
  `small_window.metrics_items` is set, the daemon keeps the device pinned
  to `BACKGROUND`, first overwrites the firmware-native clock/stats cache
  with blank payloads, and then uploads both the clock page and the custom
  metrics page host-side to avoid stale firmware overlays; the watcher
  polls `deck.yaml`'s mtime every ~1 s and triggers an atomic swap on
  change.
3. **Shutdown** — on `SIGINT`/`SIGTERM` the daemon cancels its async
   tasks, flushes the final HID packet, closes the device, and exits 0.

### Logs

By default logs are pretty-printed (`level=INFO`). Add `--verbose` for
`DEBUG`, add `--json-logs` to output one JSON object per line (this is
what the systemd unit uses so `journalctl -o json` works). On POSIX hosts
the same structured events are also mirrored to syslog by default, so
operators can inspect them with tools such as `tail -f /var/log/syslog`
when that path exists on the distro.

Key events to watch for:

| Event | Meaning |
| --- | --- |
| `daemon_started` | Startup finished; includes `pages`, `default_page`, `watch`. |
| `layout_synced` | Icons + labels uploaded to the deck. `buttons=N` tells you how many. |
| `config_reloaded` | Hot-reload applied a YAML change. |
| `small_window_pushed` | Status panel refresh tick. |
| `action_failed` | A bound action raised — payload includes `action`, `error`, `exit_code`. |

## 5. Running the editor (optional)

```bash
pip install --user '.[web]'        # one-time
ulanzi-linux gui ~/.config/ulanzi/deck.yaml
# open http://127.0.0.1:8765
```

Flags:

| Flag | Default | Notes |
| --- | --- | --- |
| `--host` | `127.0.0.1` | Anything else prints a loud loopback warning. |
| `--port` | `8765` | Pick any free TCP port. |

The editor reads / validates / writes the YAML file atomically. It
never touches USB. If a daemon is running in parallel, its watcher
picks the new file up within ~1 s — no restart needed. The GUI and the
daemon are **entirely decoupled**; either works without the other.

Every save now creates a timestamped sibling copy of `deck.yaml`. The GUI can
also save the generated upload ZIP next to the config, and the CLI exposes the
same behavior with `ulanzi-linux push-config --save-firmware`.

Icon uploads made through the GUI are normalized into 196×196 PNG files with
aspect-ratio preservation and a minimum 5 px margin. The preview slot for the
small window is also live: clock mode shows the current time, and stats mode
shows current CPU and memory readings from the host.

The same editor can also run as a desktop app on Ubuntu:

```bash
pip install --user '.[desktop]'
ulanzi-linux desktop-install
ulanzi-linux desktop ~/.config/ulanzi/deck.yaml
```

`desktop-install` writes `~/.local/share/applications/ulanzi-linux.desktop`
and the matching SVG icon under
`~/.local/share/icons/hicolor/scalable/apps/ulanzi-linux.svg`, so the editor
shows up in the Applications launcher like a normal desktop app. The desktop
window still talks only to the local FastAPI backend; it does not bypass the
same atomic-write and validation path used by the browser UI.

Both modes share the same built-in asset browser. It can import Font Awesome
application icons plus local Unicode emoji renderings into
`~/.config/ulanzi/icons/builtin/` as regular PNG files, so deck uploads keep
using the same existing image pipeline.

For HTTP API details, desktop-launcher notes, and atomic-write internals,
see [`web-ui.md`](web-ui.md).

## 6. Running as a systemd user service

```bash
./systemd/install.sh              # copies, reloads, enables, starts
systemctl --user status ulanzi-linux.service
journalctl --user -u ulanzi-linux.service -f
```

Headless / kiosk mode (no login session required):

```bash
sudo loginctl enable-linger "$USER"
```

The unit is a **user** unit (not system-wide) on purpose — the action
runner needs the session `$DISPLAY` / `$DBUS_SESSION_BUS_ADDRESS` to
launch GUI programs. Running as root would either silently no-op those
actions or need a fragile `sudo -u` dance.

Full rationale and troubleshooting in [`systemd.md`](systemd.md).

## 7. Upgrade procedure

1. **Stop the service** (if installed):

  ```bash
   systemctl --user stop ulanzi-linux.service
   ```

1. **Back up the config** — takes one second, saves your afternoon:

  ```bash
   cp ~/.config/ulanzi/deck.yaml ~/.config/ulanzi/deck.yaml.$(date +%Y%m%d).bak
   ```

1. **Pull + reinstall**:

  ```bash
   cd ~/src/ulanzi-linux
   git pull
  pip install -e ".[dev,desktop]" # or .[dev,web] if you only use the browser UI
   ```

1. **Unit changed?** If the upgrade touched `systemd/ulanzi-linux.service`,
   copy it back in:

  ```bash
   ./systemd/install.sh            # idempotent; safe to re-run
   systemctl --user daemon-reload
   ```

1. **Restart**:

  ```bash
   systemctl --user restart ulanzi-linux.service
   journalctl --user -u ulanzi-linux.service -f
   ```

Roll back by checking out the previous tag and reinstalling; `deck.yaml`
is forward-compatible within a major version.

## 8. Backup and restore

The only user-owned state is `~/.config/ulanzi/` (config + icons).
Three options, in order of "paranoia":

```bash
# Manual — quick tarball.
tar czf ulanzi-backup-$(date +%F).tgz -C "$HOME/.config" ulanzi

# Git — track config changes over time.
cd ~/.config/ulanzi && git init && git add . && git commit -m "initial"

# Borg / restic — if you already back up $HOME, make sure
# ~/.config/ulanzi is included. Icons are static assets you'd miss.
```

Restore is just extracting the tarball or `git checkout` of the file;
the daemon's watcher will pick the new YAML up on the next poll.

## 9. Observability

Structured logs via `structlog`:

- **Dev/console** — default human-friendly coloured format.
- **Production** — pass `--json-logs` (or rely on the systemd unit,
  which sets it) to emit one JSON object per line. Every event carries
  `event=<name>`, `logger=<module>`, plus domain-specific keys
  (`page`, `button_index`, `action_type`, `duration_ms`, ...).

Suggested log shipping:

```bash
journalctl -o json --user -u ulanzi-linux.service
  | vector / filebeat / fluentbit
  | Loki / Elastic / CloudWatch
```

OpenTelemetry hooks live in `src/ulanzi_linux/observability/` and are
opt-in via the `[telemetry]` extra — not required for normal operation,
useful if you fold this into a larger OTEL pipeline.

## 10. Troubleshooting

### 10.1 — `No Ulanzi D200 devices detected`

```bash
lsusb | grep 2207
ls /dev/hidraw*
```

- Nothing in `lsusb` → USB cable, port, or the deck itself. Try a
  different cable; the D200 needs data lines, not just power.
- Present in `lsusb` but no `hidraw*` node → kernel HID driver failed
  to bind. Check `dmesg | tail` for a USB error.
- Node exists but `DeviceOpenError: permission denied` → udev rule not
  loaded or user not in `plugdev`. Re-run the udev steps from §3.2 and
  **replug** the deck.

### 10.2 — Daemon flaps under systemd (`start-limit-hit`)

Five restarts in 60 s is the guardrail. Inspect the last 100 lines:

```bash
journalctl --user -u ulanzi-linux.service -n 100 --no-pager
```

Usual suspects: malformed YAML, missing icon path, device unplugged
during startup. Fix the root cause, then:

```bash
systemctl --user reset-failed ulanzi-linux.service
systemctl --user start ulanzi-linux.service
```

### 10.3 — Hot-reload isn't picking up changes

```bash
journalctl --user -u ulanzi-linux.service | grep -E 'daemon_started|config_reloaded'
```

- `watch=off` on startup → someone added `--no-watch` to the unit.
  Remove it, `daemon-reload`, restart.
- `config_reloaded` missing but you saved the file → double-check the
  path the daemon is watching matches the path you're editing (easy to
  mix `~/.config/ulanzi/deck.yaml` with a repo-local copy).

### 10.4 — Web editor says `ModuleNotFoundError: fastapi`

The `[web]` extra isn't installed:

```bash
pip install --user '.[web]'
```

### 10.5 — Desktop editor says `ModuleNotFoundError: webview` or Qt is missing

The desktop wrapper needs the desktop extra:

```bash
pip install --user '.[desktop]'
```

On Linux that extra pulls in `pywebview`, `QtPy`, `PyQt5`, and
`PyQtWebEngine`. If you only installed `.[web]`, the browser editor still
works but `ulanzi-linux desktop` will not start.

### 10.6 — Web editor loads blank

The UI now falls back to a plain textarea if CodeMirror cannot be fetched
from `cdn.jsdelivr.net`. If the page is still blank, the problem is no
longer syntax highlighting — inspect the browser console and verify the
backend is alive with `curl http://127.0.0.1:8765/api/health`.

### 10.7 — Actions don't execute from a systemd-managed daemon

Typical when running headless. The user session bus may not be where
the action expects it. The daemon now augments `$PATH` with the login
shell's search path plus the usual Snap / Flatpak export directories, so
missing graphical session variables are the more likely culprit now.
Quick check:

```bash
systemctl --user show-environment | grep -E 'DISPLAY|DBUS|WAYLAND'
```

If those are empty, your desktop session hasn't injected them into the
user manager. `systemctl --user import-environment DISPLAY DBUS_SESSION_BUS_ADDRESS WAYLAND_DISPLAY`
in your shell profile fixes it for the next login.

### 10.8 — Small window flickers or hangs

The firmware has a ~5 s watchdog. If `small_window.interval_s` is set
above that (or the daemon is blocked), the D200 falls back to Ulanzi
Studio's screensaver. Keep `interval_s` at 2.0 s (the default); if the
host is that loaded, the problem is upstream.

## 11. Safety notes

- The web editor has **no authentication** and trusts every process
  that can reach loopback. Don't bind it to a LAN IP without a reverse
  proxy that adds auth — it writes to `$HOME`.
- The action runner executes arbitrary commands from `deck.yaml`.
  Treat the config file as trusted input: whoever can write it can run
  anything your user can.
- Reverse engineering is best-effort. A firmware upgrade from Ulanzi
  could silently change the HID packet shape; if buttons stop doing
  anything after an official app update, check the protocol notes and
  open an issue.

## 12. Uninstall

```bash
systemctl --user disable --now ulanzi-linux.service
rm ~/.config/systemd/user/ulanzi-linux.service
systemctl --user daemon-reload

pip uninstall ulanzi-linux

sudo rm /etc/udev/rules.d/99-ulanzi-d200.rules
sudo udevadm control --reload-rules && sudo udevadm trigger

# Config and icons are yours — keep or remove:
# rm -rf ~/.config/ulanzi
```
