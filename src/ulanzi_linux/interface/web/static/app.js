// ulanzi-linux web editor — frontend glue.
//
// Responsibilities:
//   * Boot CodeMirror 6 with YAML syntax highlight.
//   * Keep Alpine state (dirty flag, validation summary, health) in sync.
//   * Talk to the FastAPI backend under /api/*.
//
// Why ESM + importmap + CDN instead of a bundler:
//   The whole point of shipping HTML/JS/CSS with the Python package is
//   that `pip install .[web]` gives you a working UI with no npm step.
//   CodeMirror 6's official distribution is ESM-only; jsdelivr serves
//   pre-bundled ESM at +esm, which browsers can `import` directly.

import { EditorView, basicSetup } from "https://cdn.jsdelivr.net/npm/codemirror@6.0.1/+esm";
import { EditorState } from "https://cdn.jsdelivr.net/npm/@codemirror/state@6.5.0/+esm";
import { yaml } from "https://cdn.jsdelivr.net/npm/@codemirror/lang-yaml@6.1.1/+esm";
import { oneDark } from "https://cdn.jsdelivr.net/npm/@codemirror/theme-one-dark@6.1.2/+esm";
import { keymap } from "https://cdn.jsdelivr.net/npm/@codemirror/view@6.34.0/+esm";

// Exposed on window for Alpine (defer loads Alpine after this ESM module).
window.editorApp = function editorApp() {
    return {
        // --- reactive state ------------------------------------------------
        view: null,
        health: { ok: false, version: "", config_path: "", devices_found: 0 },
        validation: null,
        status: "",
        statusClass: "",
        savedContent: "",
        dirty: false,
        busy: false,
        configPath: "",

        // --- lifecycle -----------------------------------------------------
        async init() {
            await this.refreshHealth();
            await this.loadConfig();
            this.mountEditor();
            // Periodic health refresh — cheap and lets the header reflect
            // a device being plugged in while the UI is open.
            setInterval(() => this.refreshHealth(), 5000);
        },

        // --- editor --------------------------------------------------------
        mountEditor() {
            const self = this;
            const saveKey = keymap.of([
                {
                    key: "Mod-s",
                    preventDefault: true,
                    run: () => { self.save(); return true; },
                },
                {
                    key: "Mod-Enter",
                    preventDefault: true,
                    run: () => { self.validate(); return true; },
                },
            ]);
            const onChange = EditorView.updateListener.of((v) => {
                if (!v.docChanged) return;
                const current = v.state.doc.toString();
                self.dirty = current !== self.savedContent;
            });
            const state = EditorState.create({
                doc: this.savedContent,
                extensions: [basicSetup, yaml(), oneDark, saveKey, onChange],
            });
            this.view = new EditorView({ state, parent: document.getElementById("editor") });
        },

        content() {
            return this.view ? this.view.state.doc.toString() : this.savedContent;
        },

        // --- API glue ------------------------------------------------------
        async refreshHealth() {
            try {
                const r = await fetch("/api/health");
                this.health = await r.json();
                this.configPath = this.health.config_path || "";
            } catch (e) {
                this.health = { ok: false, version: "", config_path: "", devices_found: 0 };
            }
        },

        async loadConfig() {
            try {
                const r = await fetch("/api/config");
                if (r.status === 404) {
                    // Fresh install — start with the example scaffold.
                    this.savedContent = EXAMPLE_YAML;
                    this.setStatus("new file — save to create", "");
                    return;
                }
                if (!r.ok) throw new Error(await r.text());
                const j = await r.json();
                this.savedContent = j.content;
                this.setStatus(`loaded (${j.size} bytes)`, "ok");
            } catch (e) {
                this.setStatus(`load failed: ${e.message}`, "err");
            }
        },

        async validate() {
            this.busy = true;
            this.setStatus("validating...", "");
            try {
                const r = await fetch("/api/config/validate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ content: this.content() }),
                });
                const j = await r.json();
                this.validation = j;
                this.setStatus(
                    j.ok ? "valid" : "invalid — see sidebar",
                    j.ok ? "ok" : "err",
                );
            } catch (e) {
                this.setStatus(`validate failed: ${e.message}`, "err");
            } finally {
                this.busy = false;
            }
        },

        async save() {
            if (!this.dirty) return;
            this.busy = true;
            this.setStatus("saving...", "");
            try {
                const content = this.content();
                const r = await fetch("/api/config", {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ content }),
                });
                const j = await r.json();
                this.validation = j;
                if (r.status === 422 || !j.ok) {
                    this.setStatus("rejected — fix YAML", "err");
                    return;
                }
                this.savedContent = content;
                this.dirty = false;
                this.setStatus(`saved @ ${new Date().toLocaleTimeString()}`, "ok");
            } catch (e) {
                this.setStatus(`save failed: ${e.message}`, "err");
            } finally {
                this.busy = false;
            }
        },

        revert() {
            if (!this.view) return;
            this.view.dispatch({
                changes: {
                    from: 0,
                    to: this.view.state.doc.length,
                    insert: this.savedContent,
                },
            });
            this.dirty = false;
            this.setStatus("reverted", "");
        },

        // --- helpers -------------------------------------------------------
        setStatus(text, cls) {
            this.status = text;
            this.statusClass = cls;
        },

        get shortPath() {
            if (!this.configPath) return "—";
            // Trim to last two segments so the pill stays tidy.
            const parts = this.configPath.split("/").filter(Boolean);
            return parts.length <= 2
                ? this.configPath
                : ".../" + parts.slice(-2).join("/");
        },

        get fixedBtnsLabel() {
            const idx = this.validation?.fixed_button_indices ?? [];
            return idx.length ? "[" + idx.join(", ") + "]" : "(none)";
        },
    };
};

// Minimal starter config for first-time save. Keeps the user from staring
// at an empty editor that would fail validation.
const EXAMPLE_YAML = `# ulanzi-linux deck.yaml — starter.
# See docs/config.md for the full schema.

default_page: main

small_window:
  enabled: true
  interval_s: 2.0
  time_format: "%d/%m %H:%M"

pages:
  main:
    buttons:
      - index: 0
        label: Term
        action: { type: shell, cmd: gnome-terminal }
`;
