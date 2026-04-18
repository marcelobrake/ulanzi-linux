const DECK_LAYOUT = Object.freeze([
    { index: 0, row: 1, column: 1, span: 1 },
    { index: 1, row: 1, column: 2, span: 1 },
    { index: 2, row: 1, column: 3, span: 1 },
    { index: 3, row: 1, column: 4, span: 1 },
    { index: 4, row: 1, column: 5, span: 1 },
    { index: 5, row: 2, column: 1, span: 1 },
    { index: 6, row: 2, column: 2, span: 1 },
    { index: 7, row: 2, column: 3, span: 1 },
    { index: 8, row: 2, column: 4, span: 1 },
    { index: 9, row: 2, column: 5, span: 1 },
    { index: 10, row: 3, column: 1, span: 1 },
    { index: 11, row: 3, column: 2, span: 1 },
    { index: 12, row: 3, column: 3, span: 1 },
    { index: 13, row: 3, column: 4, span: 2 },
]);

const ACTION_LABELS = Object.freeze({
    none: "Sem ação",
    shell: "Comando",
    shortcut: "Atalho",
    url: "Link",
    switch_page: "Troca de página",
});

function emptyAction() {
    return {
        type: "none",
        cmd: "",
        keys: "",
        url: "",
        page: "",
    };
}

function makeEmptyButton(index, fixed = false) {
    return {
        index,
        label: "",
        icon_path: "",
        preview_url: "",
        fixed,
        action: emptyAction(),
    };
}

function makeResetEditor(defaultPage = "main") {
    return {
        default_page: defaultPage,
        pages: [{ name: defaultPage, buttons: [] }],
        fixed_buttons: [],
        small_window: {
            enabled: true,
            interval_s: 2.0,
            time_format: "%H:%M",
            show_metrics: false,
        },
    };
}

window.editorApp = function editorApp() {
    return {
        health: { ok: false, version: "", config_path: "", devices_found: 0 },
        editor: null,
        status: "",
        statusClass: "",
        validationError: "",
        dirty: false,
        busy: false,
        selectedPage: "",
        selectedIndex: 0,
        buttonForm: null,
        newPageName: "",

        async init() {
            await this.refreshHealth();
            await this.loadEditor();
            setInterval(() => this.refreshHealth(), 5000);
        },

        async refreshHealth() {
            try {
                const response = await fetch("/api/health");
                if (!response.ok) {
                    throw new Error(await response.text());
                }
                this.health = await response.json();
            } catch (_error) {
                this.health = {
                    ok: false,
                    version: "",
                    config_path: "",
                    devices_found: 0,
                };
            }
        },

        async loadEditor() {
            this.busy = true;
            this.validationError = "";
            try {
                const response = await fetch("/api/editor");
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.detail || payload.error || "Falha ao carregar o editor");
                }
                this.editor = this.normalizeEditor(payload);
                if (!this.selectedPage || !this.editor.pages.some((page) => page.name === this.selectedPage)) {
                    this.selectedPage = this.editor.default_page || this.editor.pages[0]?.name || "main";
                }
                this.selectSlot(this.selectedIndex);
                this.dirty = false;
                this.setStatus(
                    this.editor.config_exists
                        ? "Configuração carregada"
                        : "Novo layout pronto para salvar",
                    "ok",
                );
            } catch (error) {
                this.setStatus(`Falha ao carregar: ${error.message}`, "err");
            } finally {
                this.busy = false;
            }
        },

        normalizeEditor(payload) {
            const editor = JSON.parse(JSON.stringify(payload));
            editor.pages = (editor.pages || []).map((page) => ({
                name: page.name,
                buttons: (page.buttons || []).map((button) => this.normalizeButton(button)),
            }));
            editor.fixed_buttons = (editor.fixed_buttons || []).map((button) => this.normalizeButton(button));
            editor.small_window = editor.small_window || {
                enabled: false,
                interval_s: 2.0,
                time_format: "%H:%M",
                show_metrics: true,
            };
            editor.small_window.show_metrics = editor.small_window.show_metrics !== false;
            return editor;
        },

        normalizeButton(button) {
            return {
                index: button.index,
                label: button.label || "",
                icon_path: button.icon_path || "",
                preview_url: button.preview_url || this.assetUrl(button.icon_path),
                action: { ...emptyAction(), ...(button.action || {}) },
            };
        },

        assetUrl(path) {
            return path ? `/api/asset?path=${encodeURIComponent(path)}` : "";
        },

        findButton(buttons, index) {
            return (buttons || []).find((button) => button.index === index) || null;
        },

        removeButton(buttons, index) {
            const target = buttons || [];
            const position = target.findIndex((button) => button.index === index);
            if (position !== -1) {
                target.splice(position, 1);
            }
        },

        actionLabel(type) {
            return ACTION_LABELS[type] || ACTION_LABELS.none;
        },

        selectPage(name) {
            this.selectedPage = name;
            this.selectSlot(this.selectedIndex);
        },

        selectSlot(index) {
            this.selectedIndex = index;
            this.buttonForm = this.formForIndex(index);
            this.validationError = "";
        },

        formForIndex(index) {
            const fixedButton = this.findButton(this.editor?.fixed_buttons || [], index);
            const pageButton = this.findButton(this.currentPage?.buttons || [], index);
            const source = fixedButton || pageButton;
            if (!source) {
                return makeEmptyButton(index, false);
            }
            return {
                index,
                label: source.label || "",
                icon_path: source.icon_path || "",
                preview_url: source.preview_url || this.assetUrl(source.icon_path),
                fixed: Boolean(fixedButton),
                action: { ...emptyAction(), ...(source.action || {}) },
            };
        },

        normalizeActionFromForm() {
            const action = { ...emptyAction(), ...(this.buttonForm?.action || {}) };
            switch (action.type) {
            case "shell":
                return { ...emptyAction(), type: "shell", cmd: action.cmd || "" };
            case "shortcut":
                return { ...emptyAction(), type: "shortcut", keys: action.keys || "" };
            case "url":
                return { ...emptyAction(), type: "url", url: action.url || "" };
            case "switch_page":
                return { ...emptyAction(), type: "switch_page", page: action.page || "" };
            default:
                return emptyAction();
            }
        },

        buildStateButtonFromForm() {
            return {
                index: this.selectedIndex,
                label: this.buttonForm.label || "",
                icon_path: this.buttonForm.icon_path || "",
                preview_url: this.buttonForm.preview_url || this.assetUrl(this.buttonForm.icon_path),
                action: this.normalizeActionFromForm(),
            };
        },

        isButtonMeaningful(button) {
            return Boolean(
                (button.label || "").trim()
                || (button.icon_path || "").trim()
                || button.action.type !== "none",
            );
        },

        syncSelectedButton() {
            if (!this.editor || !this.buttonForm || !this.currentPage) {
                return;
            }
            const nextButton = this.buildStateButtonFromForm();
            this.removeButton(this.editor.fixed_buttons, this.selectedIndex);
            this.removeButton(this.currentPage.buttons, this.selectedIndex);

            if (this.isButtonMeaningful(nextButton)) {
                const target = this.buttonForm.fixed
                    ? this.editor.fixed_buttons
                    : this.currentPage.buttons;
                target.push(nextButton);
                target.sort((left, right) => left.index - right.index);
            }

            this.dirty = true;
        },

        clearButton() {
            const keepFixed = this.buttonForm?.fixed || false;
            this.buttonForm = makeEmptyButton(this.selectedIndex, keepFixed);
            this.syncSelectedButton();
            this.setStatus(`Botão ${this.selectedIndex + 1} limpo`, "warn");
        },

        resetSelectedButton() {
            this.buttonForm = this.formForIndex(this.selectedIndex);
            this.setStatus(`Botão ${this.selectedIndex + 1} recarregado`, "");
        },

        handleIconPathInput() {
            this.buttonForm.preview_url = this.assetUrl(this.buttonForm.icon_path);
            this.syncSelectedButton();
        },

        clearIcon() {
            this.buttonForm.icon_path = "";
            this.buttonForm.preview_url = "";
            this.syncSelectedButton();
        },

        async uploadIcon(event) {
            const file = event.target.files?.[0];
            if (!file) {
                return;
            }
            this.busy = true;
            try {
                const form = new FormData();
                form.append("file", file);
                const response = await fetch("/api/assets", {
                    method: "POST",
                    body: form,
                });
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.detail || payload.error || "Falha no upload da imagem");
                }
                this.buttonForm.icon_path = payload.path;
                this.buttonForm.preview_url = payload.preview_url;
                this.syncSelectedButton();
                this.setStatus(`Imagem enviada: ${file.name}`, "ok");
            } catch (error) {
                this.setStatus(`Falha no upload: ${error.message}`, "err");
            } finally {
                this.busy = false;
                event.target.value = "";
            }
        },

        serializeButton(button) {
            return {
                index: button.index,
                label: button.label || "",
                icon_path: button.icon_path || null,
                action: { ...emptyAction(), ...(button.action || {}) },
            };
        },

        buildPayload() {
            return {
                default_page: this.editor.default_page,
                pages: this.editor.pages.map((page) => ({
                    name: page.name,
                    buttons: page.buttons.map((button) => this.serializeButton(button)),
                })),
                fixed_buttons: this.editor.fixed_buttons.map((button) => this.serializeButton(button)),
                small_window: {
                    enabled: Boolean(this.editor.small_window.enabled),
                    interval_s: Number(this.editor.small_window.interval_s),
                    time_format: this.editor.small_window.time_format,
                    show_metrics: this.editor.small_window.show_metrics !== false,
                },
            };
        },

        async resetDeck() {
            if (!window.confirm("Resetar o deck vai remover todos os botões configurados e deixar o visor só com a hora. Continuar?")) {
                return;
            }
            const defaultPage = this.editor?.default_page || this.selectedPage || "main";
            this.editor = this.normalizeEditor({
                ...(this.editor || {}),
                ...makeResetEditor(defaultPage),
            });
            this.selectedPage = this.editor.default_page;
            this.selectSlot(0);
            this.dirty = true;
            this.setStatus("Deck resetado. Salvando...", "warn");
            await this.saveDeck();
        },

        async validateDeck() {
            if (!this.editor) {
                return;
            }
            this.busy = true;
            this.validationError = "";
            this.setStatus("Validando layout...", "");
            try {
                const response = await fetch("/api/editor/validate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(this.buildPayload()),
                });
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.detail || payload.error || "Falha ao validar");
                }
                if (!payload.ok) {
                    this.validationError = payload.error || "Layout inválido";
                    this.setStatus("Layout inválido", "err");
                    return;
                }
                this.setStatus("Layout válido", "ok");
            } catch (error) {
                this.validationError = error.message;
                this.setStatus(`Falha ao validar: ${error.message}`, "err");
            } finally {
                this.busy = false;
            }
        },

        async saveDeck() {
            if (!this.editor || !this.dirty) {
                return;
            }
            this.busy = true;
            this.validationError = "";
            this.setStatus("Salvando layout...", "");
            try {
                const response = await fetch("/api/editor", {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(this.buildPayload()),
                });
                const payload = await response.json();
                if (!response.ok) {
                    this.validationError = payload.error || payload.detail || "Não foi possível salvar";
                    this.setStatus("Salvar falhou", "err");
                    return;
                }
                this.editor = this.normalizeEditor(payload);
                if (!this.editor.pages.some((page) => page.name === this.selectedPage)) {
                    this.selectedPage = this.editor.default_page;
                }
                this.selectSlot(this.selectedIndex);
                this.dirty = false;
                this.setStatus(
                    `Salvo e enviado ao deck às ${new Date().toLocaleTimeString()}`,
                    "ok",
                );
            } catch (error) {
                this.validationError = error.message;
                this.setStatus(`Falha ao salvar: ${error.message}`, "err");
            } finally {
                this.busy = false;
            }
        },

        addPage() {
            const nextName = this.newPageName.trim();
            if (!nextName) {
                this.setStatus("Informe um nome para a página", "err");
                return;
            }
            if (this.editor.pages.some((page) => page.name === nextName)) {
                this.setStatus(`A página ${nextName} já existe`, "err");
                return;
            }
            this.editor.pages.push({ name: nextName, buttons: [] });
            this.editor.default_page = this.editor.default_page || nextName;
            this.newPageName = "";
            this.selectedPage = nextName;
            this.selectSlot(0);
            this.dirty = true;
            this.setStatus(`Página ${nextName} criada`, "ok");
        },

        removeCurrentPage() {
            if (!this.editor || this.editor.pages.length <= 1) {
                this.setStatus("É preciso manter ao menos uma página", "err");
                return;
            }
            const removedPage = this.selectedPage;
            this.editor.pages = this.editor.pages.filter((page) => page.name !== removedPage);
            if (this.editor.default_page === removedPage) {
                this.editor.default_page = this.editor.pages[0].name;
            }
            this.editor.pages.forEach((page) => {
                page.buttons.forEach((button) => {
                    if (button.action?.type === "switch_page" && button.action.page === removedPage) {
                        button.action = emptyAction();
                    }
                });
            });
            this.editor.fixed_buttons.forEach((button) => {
                if (button.action?.type === "switch_page" && button.action.page === removedPage) {
                    button.action = emptyAction();
                }
            });
            this.selectedPage = this.editor.pages[0].name;
            this.selectSlot(this.selectedIndex);
            this.dirty = true;
            this.setStatus(`Página ${removedPage} removida`, "warn");
        },

        refreshFromDisk() {
            void this.loadEditor();
        },

        setStatus(text, cls) {
            this.status = text;
            this.statusClass = cls;
        },

        slotStyle(slot) {
            return `grid-column: ${slot.column} / span ${slot.span}; grid-row: ${slot.row};`;
        },

        buttonClasses(slot) {
            return {
                selected: slot.index === this.selectedIndex,
                fixed: slot.fixed,
                empty: slot.empty,
                wide: slot.span === 2,
            };
        },

        get currentPage() {
            return this.editor?.pages.find((page) => page.name === this.selectedPage)
                || this.editor?.pages[0]
                || null;
        },

        get deckSlots() {
            const pageButtons = this.currentPage?.buttons || [];
            return DECK_LAYOUT.map((slot) => {
                const fixedButton = this.findButton(this.editor?.fixed_buttons || [], slot.index);
                const pageButton = this.findButton(pageButtons, slot.index);
                const button = fixedButton || pageButton;
                return {
                    ...slot,
                    fixed: Boolean(fixedButton),
                    empty: !button,
                    label: button?.label || "",
                    preview_url: button?.preview_url || this.assetUrl(button?.icon_path),
                    actionLabel: this.actionLabel(button?.action?.type || "none"),
                    placeholder: slot.span === 2
                        ? `Botão ${slot.index + 1} · 2x1`
                        : `Botão ${slot.index + 1}`,
                };
            });
        },

        get currentPreviewUrl() {
            return this.buttonForm?.preview_url || this.assetUrl(this.buttonForm?.icon_path);
        },

        get shortPath() {
            const fullPath = this.health?.config_path || this.editor?.path || "";
            if (!fullPath) {
                return "—";
            }
            const parts = fullPath.split("/").filter(Boolean);
            return parts.length <= 2
                ? fullPath
                : `.../${parts.slice(-2).join("/")}`;
        },

        get selectedSlotTitle() {
            const slot = DECK_LAYOUT.find((item) => item.index === this.selectedIndex);
            if (!slot) {
                return "Botão";
            }
            const size = slot.span === 2 ? "2x1" : "1x1";
            return `Botão ${slot.index + 1} · ${size}`;
        },

        get pageOptions() {
            return this.editor?.pages.map((page) => page.name) || [];
        },

        get smallWindowSummary() {
            if (!this.editor?.small_window?.enabled) {
                return "Desligado";
            }
            return this.editor.small_window.show_metrics === false
                ? "Somente hora"
                : "Hora + CPU/Mem";
        },
    };
};
