# Web editor for `deck.yaml`

A localhost visual editor for the deck config. It is **optional** — the
CLI and daemon work fine without it — but it makes page layout, icon
uploads, small-window tuning and action review much faster than editing
the YAML by hand.

## Install

```bash
pip install --user '.[web]'
```

The `[web]` extra pulls in FastAPI, uvicorn, Font Awesome Free and the emoji
metadata package used by the built-in catalog. The core install stays
dependency-light.

For an installable desktop window on Ubuntu, use:

```bash
pip install --user '.[desktop]'
ulanzi-linux desktop-install
ulanzi-linux desktop ~/.config/ulanzi/deck.yaml
```

That writes a launcher into `~/.local/share/applications/ulanzi-linux.desktop`
plus an SVG icon under `~/.local/share/icons/hicolor/scalable/apps/`, so the
editor shows up in the desktop launcher as a normal application.

On GNOME Wayland, the desktop wrapper now selects the Qt Wayland backend
automatically when `QT_QPA_PLATFORM` was not already defined by the user.
If you need to force a different backend for debugging, export
`QT_QPA_PLATFORM` explicitly before running `ulanzi-linux desktop`.

## Run

```bash
ulanzi-linux gui ~/.config/ulanzi/deck.yaml
# open http://127.0.0.1:8765 in a browser
```

Flags:

| Flag | Default | Notes |
| --- | --- | --- |
| `--host` | `127.0.0.1` | Binding off loopback prints a loud warning. |
| `--port` | `8765` | Arbitrary, picked to not collide with common dev servers. |

The editor reads, validates and writes the YAML file. It never touches
the USB device. If a daemon is running in parallel
(`systemctl --user status ulanzi-linux.service`), its `ConfigWatcher`
picks the new file up within about a second — no restart needed.

The visual editor also supports text-only buttons: when a slot has no
image, the label is previewed centered in the tile and you can tweak
background color, text color, weight, italic, underline, font family and
font size directly from the inspector.

The current UI also exposes a denser control-room layout: the simulator
now sits immediately below the title block, uses larger deck tiles, and
keeps the summary cards just below it. The inspector still shows
action-specific help and a direct "test link" affordance for URL actions.

The simulator uses fixed 96×96 button tiles and the wide bottom-right slot
now renders a live small-window preview. When `show_metrics` is off it shows
the current clock; when it is on it shows either the firmware-native CPU /
memory preview or up to three custom Linux metrics selected in the inspector.
The small-window inspector also exposes a color picker for the strip
background; when no color is saved, the daemon uses solid black.

Leaving the metric selection empty preserves the firmware-native stats mode.
Selecting 1 to 3 items switches the strip to the Linux-rendered custom mode,
which keeps the device pinned to `BACKGROUND`, renders its own analog +
digital clock page, and can display `CPU`, `Memória`, `GPU`,
`Temperatura`, `Uso de disco`, `Rede`, or `Bateria` on the alternating
stats page.

The image inspector also ships with a built-in asset catalog backed by Font
Awesome Free plus Unicode emoji metadata rendered locally through Noto Color
Emoji when the font is present on the host. The editor can browse application
icons and emojis, search by name or keyword, and import the selected asset
directly into the user's local `icons/builtin/` directory so the deck can
upload it like any other PNG.

Image uploads are normalized immediately into 196×196 PNG assets, preserving
their aspect ratio and keeping at least 5 px of margin on every edge. Each
save also creates a timestamped sibling copy of `deck.yaml`, and the UI can
optionally persist the generated ZIP payload next to the config file.

URL actions entered through the editor are normalized on save: if the
operator pastes only a hostname like `claude.ai`, the saved action becomes
`https://claude.ai`.

The **Alternating shortcut** action takes its chords in one comma-separated
field — `F23, F24` — and saves them as a YAML list under
`action: { type: cycle_shortcut, keys: [...] }`. At least two chords are
required; a single one belongs in the plain shortcut action, and saving one
is rejected with HTTP 422 and that message in `error`. Each press sends the
next chord and wraps back to the first after the last. See
[configuration.md](configuration.md) §5.3 for where the cursor lives and when
it resets.

Below that field the inspector grows one row per chord, each with its own
icon slot — upload a file or pick from the built-in catalogue, exactly like
the button's own image. Choosing an icon for a step switches the save format
to the `steps:` spelling; with every slot left empty the compact `keys:` list
is written instead, so a config gains no noise from a feature it does not
use. Icons are positional: editing the chord field re-derives the rows and
keeps each icon on its slot number. The deck simulator shows step 1's icon
for a button that has no image of its own.

## Language

The editor ships in Portuguese (pt-BR) and English. Language is resolved
most-specific-first:

1. `?lang=` on the URL — `http://127.0.0.1:8765/?lang=en`
2. `--lang` / `$ULANZI_LANG` on the server — `ulanzi-linux gui --lang en …`
3. the browser's `Accept-Language`
4. pt-BR

```bash
ulanzi-linux gui --lang en ~/.config/ulanzi/deck.yaml
ULANZI_LANG=en ulanzi-linux gui ~/.config/ulanzi/deck.yaml
```

An unknown tag logs a warning and falls back to pt-BR, so a typo in `--lang`
degrades to the shipped UI instead of refusing to start.

### Adding a language

Catalogues are GNU gettext `.po` files under
`src/ulanzi_linux/interface/web/locales/<lang>/LC_MESSAGES/ulanzi_web.po`.
Copy the English one, replace each `msgstr`, and the language is picked up on
next start — no build step, no `msgfmt`, no code change:

```bash
cd src/ulanzi_linux/interface/web/locales
mkdir -p de/LC_MESSAGES && cp en/LC_MESSAGES/ulanzi_web.po de/LC_MESSAGES/
```

The `.po` is read directly rather than compiled to `.mo`. It is the file a
translator edits, and keeping it as the only artifact removes the class of bug
where a stale `.mo` silently overrides an edited `.po`. `msgfmt --check` still
validates these files if you want it to.

**The msgids are the original Portuguese strings.** gettext places no
constraint on the source language, and this keeps pt-BR working with no
catalogue at all — an untranslated msgid falls through unchanged. English is
therefore an ordinary translation, and an entry left empty simply shows the
Portuguese rather than showing nothing. Entries marked `#, fuzzy` are ignored
for the same reason.

Both halves of the UI share one catalogue. The HTML is translated server-side
by parsing it — text nodes plus `placeholder`, `title` and `aria-label` — so
`<script>` bodies and Alpine.js expression attributes such as `x-text` are
never touched. The JS strings go through a `t()` helper reading the catalogue
the server injects into the page, so there is no second request and no flash
of untranslated toasts. Placeholders are positional: `t("Botão {0} limpo", n)`.

`GET /api/i18n?lang=en` returns a catalogue as JSON, along with the list of
languages found on disk.

## Design

The UI is three small files under
`src/ulanzi_linux/interface/web/static/`:

* `index.html` — layout and Alpine bindings.
* `app.js` — Alpine bootstrap, API glue, editor state, and slot helpers.
* `app.css` — the local dashboard styling for the simulator and inspector.

External deps are loaded from `jsdelivr` in the browser at runtime:

* **Alpine.js 3** — reactive state without a bundler.

No npm / webpack / vite step. `pip install` is the only install command.

## Safety

### Validate before persisting

`PUT /api/config` runs the real `load_deck_config` on the payload before
touching disk. A bad paste returns `422` with the error detail and leaves
the existing file untouched.

### Atomic write

Saves use a same-directory temp file plus `os.replace`:

```text
deck.yaml          <--- target
.deck.yaml.XXXX.tmp --> fsync'd --> os.replace --> deck.yaml
```

A power loss mid-save leaves either the old file or the new, never a
truncated half. The daemon's reload path is idempotent — it reparses
on every change event, so there's no risk of reading a partial file.

### Auth and binding

The MVP has no authentication. It assumes you trust every process on
the machine that can reach `127.0.0.1`. Don't bind to a LAN IP unless
you put a reverse proxy with auth in front — the editor writes to your
home directory.

## HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Version, config path, device count — used in the UI header. |
| `GET` | `/api/devices` | Enumerate D200 units currently attached. |
| `GET` | `/api/editor` | Read the structured visual-editor payload. |
| `GET` | `/api/small-window/preview` | Return live clock and CPU/MEM values for the simulator tile. |
| `GET` | `/api/config` | Read the YAML file as text + metadata. |
| `POST` | `/api/config/validate` | Parse without saving — for live feedback. |
| `POST` | `/api/editor/validate` | Validate the structured editor payload before saving. |
| `GET` | `/api/builtin-assets` | List the built-in icon catalog available in the editor. |
| `GET` | `/api/builtin-asset` | Render a built-in icon or emoji preview as PNG. |
| `PUT` | `/api/config` | Validate, snapshot and save the raw YAML atomically. |
| `PUT` | `/api/editor` | Save the structured editor payload and optionally persist the ZIP bundle. |
| `POST` | `/api/assets` | Upload and normalize an icon into the local `icons/` folder. |
| `POST` | `/api/builtin-assets/import` | Import a built-in icon or emoji into `icons/builtin/` as PNG. |
| `GET` | `/api/asset` | Serve a stored icon back to the browser for previews. |

FastAPI auto-generates an OpenAPI spec at `/docs` while the server is
running, handy for quickly curling against the API.

## Troubleshooting

**`ModuleNotFoundError: fastapi`** — install the `[web]` extra:
`pip install --user '.[web]'`.

**Editor falls back to a plain textarea** — that's the degraded mode used
when the CodeMirror CDN is blocked. Editing and saving still work; only
syntax highlighting is lost. If you want CodeMirror back, allow
`cdn.jsdelivr.net` through your proxy.

**Changes don't apply to the deck** — the editor only writes the file.
Check that the daemon is running and watching:

```bash
systemctl --user status ulanzi-linux.service
journalctl --user -u ulanzi-linux.service | grep config_reloaded
```

If `watch=off` shows up on startup, the unit was edited with
`--no-watch` — remove it.
