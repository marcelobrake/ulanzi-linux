# Web editor for `deck.yaml`

A tiny localhost web app that lets you edit the deck config with syntax
highlighting and live validation, without learning the YAML schema by
heart. It is **optional** — the CLI and daemon work fine without it.

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

## Design

The UI is three small files under
`src/ulanzi_linux/interface/web/static/`:

* `index.html` — layout and Alpine bindings.
* `app.js` — CodeMirror bootstrap and API glue.
* `app.css` — dark theme.

External deps are loaded from `jsdelivr` in the browser at runtime:

* **CodeMirror 6** (`@codemirror/lang-yaml`, `theme-one-dark`) — syntax
  highlighting and editor.
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
| `GET`  | `/api/config` | Read the YAML file as text + metadata. |
| `POST` | `/api/config/validate` | Parse without saving — for live feedback. |
| `PUT`  | `/api/config` | Validate and save atomically. |

FastAPI auto-generates an OpenAPI spec at `/docs` while the server is
running, handy for quickly curling against the API.

## Troubleshooting

**`ModuleNotFoundError: fastapi`** — install the `[web]` extra:
`pip install --user '.[web]'`.

**Editor loads blank** — open devtools: CodeMirror comes from a CDN
and needs network access at first load. Behind a strict proxy, you can
either allow `cdn.jsdelivr.net` or vendor the JS files locally and
switch the `<script>` imports.

**Changes don't apply to the deck** — the editor only writes the file.
Check that the daemon is running and watching:

```bash
systemctl --user status ulanzi-linux.service
journalctl --user -u ulanzi-linux.service | grep config_reloaded
```

If `watch=off` shows up on startup, the unit was edited with
`--no-watch` — remove it.
