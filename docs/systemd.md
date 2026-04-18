# Running ulanzi-linux under systemd (user unit)

The project ships a ready-made **user** service unit so the daemon survives
reboots, auto-restarts on crash, and logs to journald. Running as a user
service (not system-wide) is deliberate — the daemon spawns desktop
programs and needs the session D-Bus / `$DISPLAY`, which root doesn't have.

## 1. Prerequisites

| What | Why | How |
| --- | --- | --- |
| Python package installed | Provides `~/.local/bin/ulanzi-linux` | `pip install --user .` from the repo root |
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

Manual install is trivially equivalent:

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

**`status=203/EXEC`** — systemd couldn't find `~/.local/bin/ulanzi-linux`.
Re-install the package with `pip install --user .` or adjust `ExecStart=`
in the unit to point at wherever your entry point lives
(e.g. inside a virtualenv).

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
