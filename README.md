# ulanzi-linux

Unofficial Linux client for the **Ulanzi Stream Controller D200**, built in
Python through reverse engineering of the device's USB HID protocol. Ships a
daemon, a CLI, a systemd user unit, a localhost web editor, and an
installable desktop editor for the YAML config.

> **Status:** Beta — end-to-end workflow works on real hardware, including
> daemon hot-reload, small-window sync, the built-in asset catalog, and the
> web/desktop editor flows.

## Why this exists

Ulanzi only ships official software for Windows and macOS. This project
closes the gap for Linux users by talking directly to the device over USB
HID, with no dependency on the proprietary app.

## Feature matrix

| Area | Status | Where |
| --- | --- | --- |
| Device enumeration (VID `0x2207` / PID `0x0019`) | ✅ | `ulanzi-linux devices` |
| Button event stream | ✅ | `ulanzi-linux listen` |
| LCD brightness | ✅ | `ulanzi-linux brightness N` |
| Icon + label upload (ZIP protocol) | ✅ | `ulanzi-linux push-config deck.yaml` |
| Multi-page layouts + page switchers | ✅ | `fixed_buttons` + `switch_page` action |
| Daemon with action runner (shell / shortcut / url / switch_page) | ✅ | `ulanzi-linux daemon deck.yaml` |
| YAML hot-reload (no restart) | ✅ | on by default in daemon |
| Small-window panel (clock, native stats, or up to 3 custom Linux metrics) | ✅ | `small_window:` in YAML |
| Configurable small-window background strip | ✅ | `small_window.background_color` |
| Firmware watchdog keep-alive | ✅ | absorbed by small-window loop when enabled |
| systemd **user** unit | ✅ | `systemd/ulanzi-linux.service` |
| Localhost web editor | ✅ | `ulanzi-linux gui deck.yaml` |
| Installable desktop editor | ✅ | `ulanzi-linux desktop deck.yaml` |
| Built-in icon + emoji catalog | ✅ | web/desktop editor asset browser |

## Architecture

Clean architecture, four layers, strict dependency direction (outer to inner):

```text
interface/        -> CLI, web editor (FastAPI), static assets
application/      -> Use cases: daemon, config loader, hot-reload watcher, action runner
domain/           -> Pure rules: events, button/page/config, small-window config
infrastructure/   -> HID transport, packet parsing, Ulanzi D200 spec, /proc metrics
observability/    -> Structured logging (structlog) + OpenTelemetry hooks
```

Domain depends on nothing. Infrastructure depends on domain. Application
depends on both. Interface depends on application.

## Requirements

- Python 3.11+
- Linux with a modern kernel (tested on 6.x)
- The Ulanzi D200 physical device
- `libhidapi` system library (Debian/Ubuntu: `sudo apt install libhidapi-hidraw0`)
- Optional for local emoji previews/imports: `fonts-noto-color-emoji`

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,desktop]"   # full install: web editor + desktop window
# or: pip install -e ".[dev,web]" # browser-only editor

sudo cp udev/99-ulanzi-d200.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG plugdev "$USER"   # log out / in to pick up the group
```

Then replug the deck.

## Five-minute tour

```bash
# 1. Confirm the deck is visible.
ulanzi-linux devices

# 2. Drop a starter config and push it.
mkdir -p ~/.config/ulanzi
cp examples/deck.multipage.yaml ~/.config/ulanzi/deck.yaml
ulanzi-linux push-config ~/.config/ulanzi/deck.yaml

# 3. Run the daemon in the foreground (Ctrl-C to stop).
ulanzi-linux daemon ~/.config/ulanzi/deck.yaml

# 4. Make it boot on login.
./systemd/install.sh

# 5. Edit the config in the browser.
ulanzi-linux gui ~/.config/ulanzi/deck.yaml
# open http://127.0.0.1:8765

# 6. Optional: install and launch the desktop editor.
ulanzi-linux desktop-install
ulanzi-linux desktop ~/.config/ulanzi/deck.yaml
```

The editor exposes the same config model in both browser and desktop modes.
Its built-in asset browser can import more than 2000 Font Awesome icons plus
Unicode emojis rendered locally when `Noto Color Emoji` is available on the
host; imported assets are saved into `~/.config/ulanzi/icons/builtin/` and
then uploaded to the deck through the normal PNG pipeline.

## Documentation

- [Operations manual](docs/operations.md) — install, run, upgrade, back up, troubleshoot.
- [Configuration reference](docs/configuration.md) — every YAML field explained.
- [systemd user unit](docs/systemd.md) — service file, install, logs.
- [Web and desktop editor](docs/web-ui.md) — GUI details, built-in asset catalog, desktop launcher, HTTP API.
- [Architecture notes](docs/architecture.md) — layer boundaries and decisions.
- [Protocol notes](docs/protocol.md) — HID packet format, commands, quirks.

## Credits and prior art

This project would not exist without the reverse-engineering work of the
community:

- **[redphx/strmdck](https://github.com/redphx/strmdck)** — the original
  Python library that mapped the D200 HID protocol. Executable documentation
  for everything we implement here.
- **[redphx/homedeck](https://github.com/redphx/homedeck)** — Home Assistant
  integration built on top of strmdck, excellent reference for icon rendering.
- **[UlanziTechnology/UlanziDeckPlugin-SDK](https://github.com/UlanziTechnology/UlanziDeckPlugin-SDK)**
  — the official plugin SDK for the Windows/Mac app, useful for manifest and
  icon-size cross-checks.
- **[Hackaday coverage](https://hackaday.com/tag/ulanzi-d200/)** — revealed the
  device runs Linux 5.10 on a Rockchip RK3308HS with open ADB root.

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

This project is **not affiliated with Ulanzi or Fuzhou Rockchip Electronics**.
"Ulanzi" and "Stream Controller D200" are trademarks of their respective
owners. Use at your own risk — reverse engineering inherently carries the
risk of unintended device behavior.
