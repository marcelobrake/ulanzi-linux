# Running ulanzi-linux under systemd (user unit)

The project ships a ready-made **user** service unit so the daemon survives
reboots, auto-restarts on crash, and logs to journald. Running as a user
service (not system-wide) is deliberate — the daemon spawns desktop
programs and needs the session D-Bus / `$DISPLAY`, which root doesn't have.

## 1. Prerequisites

| What | Why | How |
| --- | --- | --- |
| Python package installed | Provides the `ulanzi-linux` entry point used by the user unit | `pip install --user .` or install it in your active pyenv / virtualenv |
| udev rule installed | Grants hidraw access without sudo | `sudo cp udev/99-ulanzi-d200.rules /etc/udev/rules.d/ && sudo udevadm control --reload-rules && sudo udevadm trigger` |
| User in `plugdev` group | Required by the udev rule | `sudo usermod -aG plugdev $USER` (then log out / in) |
| Deck YAML in place | The daemon refuses to start without one | `mkdir -p ~/.config/ulanzi && cp examples/deck.multipage.yaml ~/.config/ulanzi/deck.yaml` |

Sanity-check the entry point is on `$PATH`:

```bash
which ulanzi-linux
ulanzi-linux devices
```

If `which` comes back empty, either `pip install --user` skipped
`~/.local/bin` from `$PATH` (fix your shell rc) or the install failed.

## 2. Install the unit

The fastest path is the helper script:

```bash
./systemd/install.sh            # copies, reloads, enables, starts
./systemd/install.sh --dry-run  # preview commands without touching anything
./systemd/install.sh --uninstall
```

The helper script resolves the actual `ulanzi-linux` executable from your
current shell first. That matters on hosts that install the package via
pyenv or a virtual environment, where the console script does not live in
`~/.local/bin`. The same helper also installs a desktop autostart entry
for the graphical-session bridge at `~/.config/autostart/ulanzi-linux-session-agent.desktop`,
plus the desktop editor launcher under
`~/.local/share/applications/ulanzi-linux.desktop` with the resolved absolute
console-script path so GNOME does not hide it when the graphical session uses
a narrower `$PATH` than your terminal.

The daemon keeps running under the user systemd manager, but shell / URL /
shortcut actions can now be delegated to a second process started by the
desktop session itself. That bridge listens on a Unix socket inside
`$XDG_RUNTIME_DIR` and runs commands from the already-initialized graphical
environment.

Manual install is only trivially equivalent when your entry point really
lives at `~/.local/bin/ulanzi-linux`. Otherwise either use the helper
script or edit `ExecStart=` to the resolved executable path.

Typical paths:

```bash
command -v ulanzi-linux
pyenv which ulanzi-linux     # when using pyenv
```

Manual install:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/ulanzi-linux.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ulanzi-linux.service
```

## 3. Verify

```bash
systemctl --user status ulanzi-linux.service
journalctl --user -u ulanzi-linux.service -f
```

A healthy startup looks like:

```text
ulanzi-linux: daemon_started pages=['main','media','dev'] default_page=main
ulanzi-linux: layout_synced page=main buttons=16
ulanzi-linux: small_window_started interval_s=2.0
```

…and the D200 shows your configured layout instead of Ulanzi Studio's
built-in screensaver.

For the graphical-session bridge, a healthy manual start looks like:

```bash
ulanzi-linux --json-logs session-agent
```

```text
session-agent running — socket='/run/user/1000/ulanzi-linux-session-agent.sock'
```

If the deck power-cycles while the unit is already running, the daemon now
waits for the HID node to come back, reconnects automatically, and reapplies
the last known layout / brightness / small-window state without needing a
manual `systemctl --user restart`.

## 4. Common operations

```bash
# Edit the YAML — the daemon hot-reloads on save, no restart needed.
vi ~/.config/ulanzi/deck.yaml

# Force-restart after a package upgrade.
systemctl --user restart ulanzi-linux.service

# Temporarily stop (e.g. to run `ulanzi-linux listen` from the shell).
systemctl --user stop ulanzi-linux.service

# Turn it off permanently.
systemctl --user disable --now ulanzi-linux.service
```

## 5. Troubleshooting

**`status=203/EXEC`** — systemd couldn't execute the configured
`ExecStart=` path. Most often the package was installed via pyenv or a
virtualenv, but the unit still points at `~/.local/bin/ulanzi-linux`.
Re-run `./systemd/install.sh` from the environment where `ulanzi-linux`
works, or adjust `ExecStart=` to the resolved path from `command -v
ulanzi-linux` / `pyenv which ulanzi-linux`.

**`DeviceOpenError: permission denied`** — udev rule not loaded or user
not in `plugdev`. Re-run the udev install commands from §1 and **replug**
the deck; udev only fires on device events.

**Unit flaps (`start-limit-hit`)** — 5 restarts in 60 s triggers the
fail-safe. Inspect the last log lines before the failure:

```bash
journalctl --user -u ulanzi-linux.service -n 100 --no-pager
```

Usual suspects: malformed YAML (parse error logs the path and the pyyaml
message), missing icon file referenced by a button, or the device being
unplugged while the daemon was starting.

**No restart on YAML save** — confirm the watcher is on:
`journalctl --user -u ulanzi-linux.service | grep daemon_started` and
look for `watch=on`. If it says `off`, somebody edited the unit to pass
`--no-watch` — remove it.

**Buttons still don't open GUI apps after upgrading** — confirm the
session agent is running in the desktop session and that the socket exists:

```bash
ls -l "$XDG_RUNTIME_DIR/ulanzi-linux-session-agent.sock"
pgrep -af "ulanzi-linux --json-logs session-agent"
```

If needed, start it manually in the current session:

```bash
ulanzi-linux --json-logs session-agent
```

**Logs are verbose** — structured JSON is the default in this unit to
make log shipping (Loki, Elastic, CloudWatch) painless. For a friendlier
console view, run the daemon manually:

```bash
systemctl --user stop ulanzi-linux.service
ulanzi-linux daemon ~/.config/ulanzi/deck.yaml
```

## 6. Why not a system-wide unit?

You *can* wire this into `/etc/systemd/system/` and run as root, but:

* `xdg-open`, `gnome-terminal`, `xdotool`, browsers — all need the user
  session's `$DISPLAY`, `$DBUS_SESSION_BUS_ADDRESS` and `$XAUTHORITY`.
  Root has none of those by default.
* The hidraw node belongs to the logged-in user via `uaccess`, not root,
  so a system unit would need `/dev/hidraw*` permissions hacks.
* Multi-user boxes would each need their own config anyway.

If you really need it running without a login session (headless kiosk,
digital-signage rig), use `loginctl enable-linger $USER` — systemd will
keep the user manager alive across logouts and the existing user unit
starts at boot.
