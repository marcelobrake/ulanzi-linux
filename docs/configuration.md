# ulanzi-linux — Configuration reference

Full schema for `deck.yaml`. Canonical example:
[`examples/deck.multipage.yaml`](../examples/deck.multipage.yaml).

The file is parsed by `ulanzi_linux.application.config_loader.load_deck_config`.
That function is the source of truth; this doc mirrors it.

## 1. Top-level shape

```yaml
default_page: <page-name>       # required for multi-page configs
small_window:                   # optional block
  enabled: false                # default false
  interval_s: 2.0
  time_format: "%d/%m %H:%M"
pages:                          # multi-page schema (preferred)
  <page-name>:
    buttons:
      - index: <int>
        label: <string>
        icon: <path>
        action: { type: <string>, ... }
  <page-name>:
    buttons: [...]
fixed_buttons:                  # optional; rendered on every page
  - index: <int>
    ...
```

A **legacy single-page schema** is also accepted for backwards
compatibility (see §6). New configs should always use `pages:`.

## 2. `default_page`

Required for multi-page configs. The page the daemon activates at
startup and after every hot-reload.

- Must exist as a key in `pages`.
- Validation raises `ValueError` with the available page names if not.

```yaml
default_page: main
pages:
  main: { buttons: [] }
```

## 3. `small_window`

The D200 has a narrow LCD strip to the left of the button grid, meant
for status info. When `enabled: true`, the daemon pushes a large clock
on top with CPU% / memory% underneath at `interval_s` cadence. When disabled, a plain heartbeat
loop runs in its place (to keep the firmware watchdog happy).

| Field | Type | Default | Constraints |
| --- | --- | --- | --- |
| `enabled` | bool | `false` | — |
| `interval_s` | float | `2.0` | `0.05 ≤ x ≤ 4.5`. Below → busy-loop risk. Above → device falls back to standalone screensaver after the ~5 s firmware watchdog. |
| `time_format` | string | `"%H:%M"` | Any `strftime` pattern. Keep it short — the firmware uses a larger clock layout when the string is compact. |

```yaml
small_window:
  enabled: true
  interval_s: 2.0
  time_format: "%H:%M"          # large centered clock on top
```

### Why no GPU metric?

Brake explicitly dropped it — no portable way to get utilization
across Intel / AMD / NVIDIA without pulling in heavy drivers. If you
want it, add a custom metric in
`src/ulanzi_linux/infrastructure/system_metrics.py` and submit a PR.

## 4. `pages`

A dict of named pages. Each page has its own list of buttons. The
daemon renders the active page's buttons plus any `fixed_buttons`.

```yaml
pages:
  main:
    buttons:
      - index: 0
        label: Term
        action: { type: shell, cmd: gnome-terminal }
  media:
    buttons:
      - index: 0
        label: Play
        action: { type: shortcut, keys: XF86AudioPlay }
```

### Button fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `index` | int | yes | Physical touch position (0-based). The D200 renders buttons only on indices 0–12. Index 13 is the wide info window: it can trigger an action on touch, but its visual content still comes from `small_window`. |
| `label` | string | no | Text rendered on the button. Defaults to `""`. |
| `icon` | string (path) | no | PNG/JPG path. `~` is expanded. Icons are resized to the D200's expected format automatically. |
| `text_style` | object | no | Used when the button has no `icon`. The label is rendered into the tile itself, centered both vertically and horizontally. |
| `action` | object | no | What to run on press. If absent, the button is visual-only. See §5. |

`index` uniqueness is enforced **across** page + fixed buttons. A page
cannot reuse an index used by `fixed_buttons` — the config loader
raises `ValueError` with the colliding indices before the device is
touched.

### `text_style`

Optional block for text-only buttons:

```yaml
pages:
  main:
    buttons:
      - index: 0
        label: OpenAI
        text_style:
          background_color: "#102030"
          text_color: "#F0F0F0"
          bold: true
          italic: false
          underline: false
          font_family: DejaVu Sans
          font_size: 34
```

Supported fields:

| Field | Type | Default |
| --- | --- | --- |
| `background_color` | hex color | `#111827` |
| `text_color` | hex color | `#F8FAFC` |
| `bold` | bool | `false` |
| `italic` | bool | `false` |
| `underline` | bool | `false` |
| `font_family` | string | `DejaVu Sans` |
| `font_size` | int | `30` |

These settings are ignored when `icon` is present, because the firmware's
own label overlay is then used for the caption.

## 5. Actions

`action` is a discriminated union on the `type` field. Four action
types are recognised today.

### 5.1 — `shell`

Run an arbitrary shell command. The full string is passed to the shell
via `subprocess`, so pipes / env expansion / quoting all work.

```yaml
action: { type: shell, cmd: "gnome-terminal -- bash -lc 'docker ps; exec bash'" }
```

**Security note**: the config file is trusted input. Whatever can write
`deck.yaml` can run anything your user can.

### 5.2 — `shortcut`

Emit a keyboard shortcut via `xdotool` (X11) or `ydotool` (Wayland).
Key names follow the underlying tool's grammar — `ctrl+alt+t`,
`XF86AudioPlay`, `Super_L`.

```yaml
action: { type: shortcut, keys: "ctrl+alt+t" }
action: { type: shortcut, keys: "XF86AudioPlay" }
```

Relies on the daemon running inside a session where `$DISPLAY` /
`$WAYLAND_DISPLAY` are set — hence the user-unit choice for systemd.

### 5.3 — `url`

Open a URL with `xdg-open`. Respects your default browser.

```yaml
action: { type: url, url: "https://claude.ai" }
```

### 5.4 — `switch_page`

The only action intercepted by the daemon itself; never hits the action
runner. Swaps the active page and re-syncs the layout.

```yaml
action: { type: switch_page, page: media }
```

The target `page` must exist in `pages:` — otherwise the action is a
no-op and a warning is logged.

## 6. `fixed_buttons`

Buttons rendered on **every** page, in addition to the active page's
own buttons. Typically the physical bottom row (indices 10, 11, 12)
used as page switchers — so the navigation row is always visible no
matter where you are.

Same schema as a page button:

```yaml
fixed_buttons:
  - index: 10
    label: Main
    action: { type: switch_page, page: main }
  - index: 11
    label: Media
    action: { type: switch_page, page: media }
  - index: 12
    label: Dev
    action: { type: switch_page, page: dev }
```

Indices in `fixed_buttons` **cannot** collide with any page button
index — validation fails at load time. Index 13 is valid here too, but
only as an action target; icon/label are ignored for that slot.

## 7. Legacy single-page schema

For backwards compatibility, a flat `buttons:` at the top level is
still accepted and normalised into a single page named `default`:

```yaml
buttons:
  - index: 0
    label: Term
    action: { type: shell, cmd: gnome-terminal }
```

Equivalent to:

```yaml
default_page: default
pages:
  default:
    buttons:
      - index: 0
        label: Term
        action: { type: shell, cmd: gnome-terminal }
```

`small_window` still works with the legacy schema; `fixed_buttons`
does not (there's only one page — it would be redundant).

## 8. Icon assets

Icons can be any format Pillow opens (PNG, JPG, WebP). They are:

1. Loaded from disk.
2. Resized to the D200's expected dimensions (72×72 at present).
3. Re-encoded as PNG inside the ZIP that the HID protocol expects.

Tips:

- Keep icons in `~/.config/ulanzi/icons/` — the examples assume this.
- Transparent PNGs work; transparency becomes the device's default
  dark background.
- Missing paths fail **validation**, not runtime — the web editor's
  `POST /api/config/validate` catches them before save.

## 9. Hot-reload semantics

The daemon watches the YAML file's mtime every ~1 s (`ConfigWatcher`).
On change:

1. Reparse via `load_deck_config`.
2. On success, atomic-swap the live `DeckConfig` reference.
3. Sync the layout (re-upload icons + labels).
4. Emit `config_reloaded` with the new `pages`, `default_page`, and
   `buttons` count.

On parse failure, the old config stays active; the daemon logs
`config_reload_failed` with the error. **Your deck never enters a
broken state from a bad save.**

The web editor reinforces this by validating *before* writing
(`POST /api/config/validate`) and by using atomic disk writes — so
even a power loss mid-save leaves the old file intact.

## 10. Full annotated example

```yaml
# Day-to-day layout for a dev machine.
default_page: main

small_window:
  enabled: true
  interval_s: 2.0
  time_format: "%d/%m %H:%M"

# Always-visible page switchers (bottom row).
fixed_buttons:
  - index: 10
    label: Main
    action: { type: switch_page, page: main }
  - index: 11
    label: Media
    action: { type: switch_page, page: media }
  - index: 12
    label: Dev
    action: { type: switch_page, page: dev }

pages:
  main:
    buttons:
      - index: 0
        icon: ~/.config/ulanzi/icons/terminal.png
        label: Term
        action: { type: shell, cmd: gnome-terminal }
      - index: 1
        icon: ~/.config/ulanzi/icons/claude.png
        label: Claude
        action: { type: url, url: https://claude.ai }
      - index: 2
        icon: ~/.config/ulanzi/icons/screenshot.png
        label: Shot
        action: { type: shell, cmd: gnome-screenshot -i }

  media:
    buttons:
      - { index: 0, label: Play, action: { type: shortcut, keys: XF86AudioPlay } }
      - { index: 1, label: Prev, action: { type: shortcut, keys: XF86AudioPrev } }
      - { index: 2, label: Next, action: { type: shortcut, keys: XF86AudioNext } }
      - { index: 3, label: Mute, action: { type: shortcut, keys: XF86AudioMute } }
      - { index: 4, label: Vol-, action: { type: shortcut, keys: XF86AudioLowerVolume } }
      - { index: 5, label: Vol+, action: { type: shortcut, keys: XF86AudioRaiseVolume } }

  dev:
    buttons:
      - { index: 0, label: VSCode, action: { type: shell, cmd: code } }
      - { index: 1, label: GH,     action: { type: url,   url: https://github.com } }
      - { index: 2, label: "Docker PS", action: { type: shell, cmd: "gnome-terminal -- bash -lc 'docker ps; exec bash'" } }
```
