// ulanzi-linux web editor — frontend glue.
//
// Responsibilities:
//   * Boot Alpine state before Alpine itself scans the DOM.
//   * Upgrade to CodeMirror 6 when the CDN is reachable.
//   * Fall back to a plain textarea when CodeMirror cannot be loaded.
//   * Talk to the FastAPI backend under /api/*.

const CODEMIRROR_URLS = {
    state: "https://cdn.jsdelivr.net/npm/@codemirror/state@6.5.0/+esm",
    view: "https://cdn.jsdelivr.net/npm/@codemirror/view@6.34.0/+esm",
    yaml: "https://cdn.jsdelivr.net/npm/@codemirror/lang-yaml@6.1.1/+esm",
    theme: "https://cdn.jsdelivr.net/npm/@codemirror/theme-one-dark@6.1.2/+esm",
};

window.editorApp = function editorApp() {
    return {
        view: null,
        textarea: null,
        health: { ok: false, version: "", config_path: "", devices_found: 0 },
        validation: null,
        status: "",
        statusClass: "",
        savedContent: "",
        dirty: false,
        busy: false,
        configPath: "",
        editorMode: "loading",

        async init() {
            await this.refreshHealth();
            await this.loadConfig();
            await this.mountEditor();
            await this.refreshValidation({ preserveStatus: true });
            setInterval(() => this.refreshHealth(), 5000);
        },

        async mountEditor() {
            const host = document.getElementById("editor");
            host.replaceChildren();
            this.view = null;
            this.textarea = null;

            try {
                const [
                    { EditorState },
                    { EditorView, keymap },
                    { yaml },
                    { oneDark },
                ] = await Promise.all([
                    import(CODEMIRROR_URLS.state),
                    import(CODEMIRROR_URLS.view),
                    import(CODEMIRROR_URLS.yaml),
                    import(CODEMIRROR_URLS.theme),
                ]);

                const self = this;
                const saveKey = keymap.of([
                    {
                        key: "Mod-s",
                        preventDefault: true,
                        run: () => {
                            void self.save();
                            return true;
                        },
                    },
                    {
                        key: "Mod-Enter",
                        preventDefault: true,
                        run: () => {
                            void self.validate();
                            return true;
                        },
                    },
                ]);
                const onChange = EditorView.updateListener.of((update) => {
                    if (!update.docChanged) {
                        return;
                    }
                    self.dirty = update.state.doc.toString() !== self.savedContent;
                });
                const state = EditorState.create({
                    doc: this.savedContent,
                    extensions: [
                        EditorView.lineWrapping,
                        yaml(),
                        oneDark,
                        saveKey,
                        onChange,
                    ],
                });
                this.view = new EditorView({ state, parent: host });
                this.editorMode = "codemirror";
            } catch (error) {
                this.mountTextarea(host);
                this.editorMode = "textarea";
                console.warn("CodeMirror unavailable, falling back to textarea", error);
            }
        },

        mountTextarea(host) {
            const textarea = document.createElement("textarea");
            textarea.id = "editor-textarea";
            textarea.className = "editor-textarea";
            textarea.spellcheck = false;
            textarea.value = this.savedContent;
            textarea.addEventListener("input", () => {
                this.dirty = textarea.value !== this.savedContent;
            });
            host.appendChild(textarea);
            this.textarea = textarea;
        },

        setEditorContent(content) {
            if (this.view) {
                this.view.dispatch({
                    changes: {
                        from: 0,
                        to: this.view.state.doc.length,
                        insert: content,
                    },
                });
                return;
            }
            if (this.textarea) {
                this.textarea.value = content;
            }
        },

        content() {
            if (this.view) {
                return this.view.state.doc.toString();
            }
            if (this.textarea) {
                return this.textarea.value;
            }
            return this.savedContent;
        },

        async refreshHealth() {
            try {
                const r = await fetch("/api/health");
                if (!r.ok) {
                    throw new Error(await r.text());
                }
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
                    this.savedContent = EXAMPLE_YAML;
                    this.validation = null;
                    this.setEditorContent(this.savedContent);
                    this.dirty = false;
                    this.setStatus("new file — save to create", "");
                    return;
                }
                if (!r.ok) throw new Error(await r.text());
                const j = await r.json();
                this.savedContent = j.content;
                this.setEditorContent(this.savedContent);
                this.dirty = false;
                this.setStatus(`loaded (${j.size} bytes)`, "ok");
            } catch (e) {
                this.setStatus(`load failed: ${e.message}`, "err");
            }
        },

        async refreshValidation({ preserveStatus = false } = {}) {
            try {
                const r = await fetch("/api/config/validate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ content: this.content() }),
                });
                if (!r.ok) {
                    throw new Error(await r.text());
                }
                const j = await r.json();
                this.validation = j;
                if (!preserveStatus) {
                    this.setStatus(
                        j.ok ? "valid" : "invalid — see sidebar",
                        j.ok ? "ok" : "err",
                    );
                }
                return j;
            } catch (e) {
                this.validation = {
                    ok: false,
                    error: `validate failed: ${e.message}`,
                    pages: [],
                    fixed_button_indices: [],
                    small_window_enabled: false,
                };
                if (!preserveStatus) {
                    this.setStatus(this.validation.error, "err");
                }
                return this.validation;
            }
        },

        async validate() {
            this.busy = true;
            this.setStatus("validating...", "");
            try {
                await this.refreshValidation();
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
                this.setEditorContent(content);
                this.dirty = false;
                this.setStatus(`saved @ ${new Date().toLocaleTimeString()}`, "ok");
            } catch (e) {
                this.setStatus(`save failed: ${e.message}`, "err");
            } finally {
                this.busy = false;
            }
        },

        revert() {
            this.setEditorContent(this.savedContent);
            this.dirty = false;
            this.setStatus("reverted", "");
            void this.refreshValidation({ preserveStatus: true });
        },

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
