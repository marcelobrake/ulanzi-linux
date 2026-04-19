# ulanzi-linux

Unofficial Linux client for the **Ulanzi Stream Controller D200**, built in
Python through reverse engineering of the device's USB HID protocol. Ships a
daemon, a CLI, a systemd user unit, and a localhost web editor for the YAML
config.

> **Status:** Beta — end-to-end workflow works on real hardware. 71 tests
> passing in CI.

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
| Small-window panel (clock or CPU / mem stats) | ✅ | `small_window:` in YAML |
| Firmware watchdog keep-alive | ✅ | absorbed by small-window loop when enabled |
| systemd **user** unit | ✅ | `systemd/ulanzi-linux.service` |
| Localhost web editor | ✅ | `ulanzi-linux gui deck.yaml` |

## Architecture

Clean architecture, four layers, strict dependency direction (outer to inner):

```
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

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,web]"     # web extra enables the GUI

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
```

## Documentation

- [Operations manual](docs/operations.md) — install, run, upgrade, back up, troubleshoot.
- [Configuration reference](docs/configuration.md) — every YAML field explained.
- [systemd user unit](docs/systemd.md) — service file, install, logs.
- [Web editor](docs/web-ui.md) — GUI details, HTTP API, atomic write.
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
