# Web editor for `deck.yaml`

A localhost visual editor for the deck config. It is **optional** — the
CLI and daemon work fine without it — but it makes page layout, icon
uploads, small-window tuning and action review much faster than editing
the YAML by hand.

## Install

```bash
pip install --user '.[web]'
```

The `[web]` extra pulls in FastAPI and uvicorn. The core install stays
dependency-light.

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
the current clock; when it is on it shows live CPU and memory values from the
host, matching the D200 mode switch already validated on hardware. The small-
window inspector also exposes a color picker for the strip background; when no
color is saved, the daemon uses solid black.

The image inspector also ships with a built-in icon catalog backed by Font
Awesome Free. The editor can browse more than 2000 built-in icons, search by
name or keyword, and import the selected asset directly into the user's local
`icons/builtin/` directory so the deck can upload it like any other PNG.

Image uploads are normalized immediately into 196×196 PNG assets, preserving
their aspect ratio and keeping at least 5 px of margin on every edge. Each
save also creates a timestamped sibling copy of `deck.yaml`, and the UI can
optionally persist the generated ZIP payload next to the config file.

URL actions entered through the editor are normalized on save: if the
operator pastes only a hostname like `claude.ai`, the saved action becomes
`https://claude.ai`.

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

```
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
| `GET`  | `/api/health` | Version, config path, device count — used in the UI header. |
| `GET`  | `/api/devices` | Enumerate D200 units currently attached. |
| `GET`  | `/api/editor` | Read the structured visual-editor payload. |
| `GET`  | `/api/small-window/preview` | Return live clock and CPU/MEM values for the simulator tile. |
| `GET`  | `/api/config` | Read the YAML file as text + metadata. |
| `POST` | `/api/config/validate` | Parse without saving — for live feedback. |
| `POST` | `/api/editor/validate` | Validate the structured editor payload before saving. |
| `PUT`  | `/api/config` | Validate, snapshot and save the raw YAML atomically. |
| `PUT`  | `/api/editor` | Save the structured editor payload and optionally persist the ZIP bundle. |
| `POST` | `/api/assets` | Upload and normalize an icon into the local `icons/` folder. |
| `GET`  | `/api/asset` | Serve a stored icon back to the browser for previews. |

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
