# ulanzi-linux

Unofficial Linux client for the **Ulanzi Stream Controller D200**, built in Python
through reverse engineering of the device's USB HID protocol.

> Status: **Alpha** — active development, MVP (button events + brightness) is the
> first milestone. See `docs/roadmap.md`.

## Why this exists

Ulanzi only ships official software for Windows and macOS. This project closes
the gap for Linux users by talking directly to the device over USB HID, with
no dependency on the proprietary app.

## What works

- [x] USB identification (VID `0x2207`, PID `0x0019`) confirmed
- [x] HID packet framing (`0x7C 0x7C` + command + length + payload, 1024-byte frames)
- [ ] Button press detection (in progress)
- [ ] Brightness control
- [ ] Label style configuration
- [ ] Small window data (clock/stats/background)
- [ ] Icon upload (ZIP-based, with firmware bug workaround)
- [ ] Profile/page management
- [ ] Daemon + IPC
- [ ] GUI

## Architecture

Clean architecture, four layers, strict dependency direction (outer to inner):

```
interface/        -> CLI, future GUI, future REST API
application/      -> Use cases, service orchestration
domain/           -> Pure business rules: events, value objects, device abstractions
infrastructure/   -> HID transport, packet parsing, concrete Ulanzi D200 implementation
observability/    -> Structured logging (structlog) + OpenTelemetry hooks
```

Domain depends on nothing. Infrastructure depends on domain. Application depends
on both. Interface depends on application.

## Requirements

- Python 3.11+
- Linux with a modern kernel (tested on 6.x)
- The Ulanzi D200 physical device
- `libhidapi` system library (Debian/Ubuntu: `sudo apt install libhidapi-hidraw0`)

## Installation (development)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install the udev rule so you don't need sudo to access the device:
sudo cp udev/99-ulanzi-d200.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Replug the device after installing the rule.

## Quick start

```bash
ulanzi-linux devices        # enumerate connected Ulanzi decks
ulanzi-linux listen         # stream button events to stdout
ulanzi-linux brightness 50  # set brightness (0-100)
```

## Credits and prior art

This project would not exist without the reverse engineering work of the community:

- **[redphx/strmdck](https://github.com/redphx/strmdck)** — the original Python
  library that mapped the D200 HID protocol. We use it as executable documentation
  of the protocol and re-implement the concepts here with clean architecture,
  observability, and tests.
- **[redphx/homedeck](https://github.com/redphx/homedeck)** — Home Assistant
  integration built on top of strmdck, excellent reference for icon rendering.
- **[Hackaday coverage](https://hackaday.com/tag/ulanzi-d200/)** — revealed the
  device runs Linux 5.10 on a Rockchip RK3308HS with open ADB root.

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

This project is **not affiliated with Ulanzi or Fuzhou Rockchip Electronics**.
"Ulanzi" and "Stream Controller D200" are trademarks of their respective owners.
Use at your own risk — reverse engineering inherently carries the risk of
unintended device behavior.
