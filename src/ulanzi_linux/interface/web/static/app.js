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
    { index: 13, row: 3, column: 4, span: 2, kind: "info" },
]);

const INFO_WINDOW_INDEX = 13;
const FONT_OPTIONS = Object.freeze([
    "DejaVu Sans",
    "DejaVu Serif",
    "DejaVu Sans Mono",
    "Liberation Sans",
    "Liberation Serif",
]);

const ACTION_LABELS = Object.freeze({
    none: "Sem ação",
    shell: "Comando",
    shortcut: "Atalho",
    predefined_command: "Comando pré-definido",
    url: "Link",
    switch_page: "Troca de página",
});

const BUILTIN_ICON_STYLES = Object.freeze([
    { value: "all", label: "Todos" },
    { value: "brands", label: "Apps/brands" },
    { value: "emoji", label: "Emojis" },
    { value: "regular", label: "Regular" },
    { value: "solid", label: "Solid" },
]);

const SMALL_WINDOW_METRICS = Object.freeze([
    { value: "cpu", label: "CPU" },
    { value: "memory", label: "Memória" },
    { value: "gpu", label: "GPU" },
    { value: "temperature", label: "Temperatura" },
    { value: "disk", label: "Uso de disco" },
    { value: "network", label: "Rede" },
    { value: "battery", label: "Bateria" },
]);

function emptyAction() {
    return {
        type: "none",
        cmd: "",
        keys: "",
        command_id: "",
        url: "",
        page: "",
    };
}

function emptyTextStyle() {
    return {
        background_color: "#111827",
        text_color: "#F8FAFC",
        bold: false,
        italic: false,
        underline: false,
        font_family: "DejaVu Sans",
        font_size: 30,
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
        text_style: emptyTextStyle(),
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
            rotate_every_s: null,
            background_color: "#000000",
            metrics_items: [],
        },
    };
}

window.editorApp = function editorApp() {
    return {
        health: { ok: false, version: "", config_path: "", devices_found: 0 },
        editor: makeResetEditor(),
        saveFirmwareBundle: false,
        smallWindowPreview: {
            time_text: "--:--",
            cpu_percent: 0,
            mem_percent: 0,
            gpu_percent: 0,
            metrics: [],
        },
        status: "",
        statusClass: "",
        validationError: "",
        dirty: false,
        busy: false,
        selectedPage: "main",
        selectedIndex: 0,
        buttonForm: makeEmptyButton(0, false),
        newPageName: "",
        fontOptions: FONT_OPTIONS,
        builtinIconStyles: BUILTIN_ICON_STYLES,
        smallWindowMetricOptions: SMALL_WINDOW_METRICS,
        builtinIcons: [],
        builtinIconQuery: "",
        builtinIconStyle: "all",
        showBuiltinIconBrowser: false,

        async init() {
            await this.refreshHealth();
            await this.loadBuiltinIcons();
            await this.loadEditor();
            await this.refreshSmallWindowPreview();
            setInterval(() => this.refreshHealth(), 5000);
            setInterval(() => {
                void this.refreshSmallWindowPreview();
            }, 1000);
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

        async loadBuiltinIcons() {
            try {
                const response = await fetch("/api/builtin-assets");
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.detail || payload.error || "Falha ao carregar catálogo");
                }
                this.builtinIcons = payload.items || [];
            } catch (error) {
                this.builtinIcons = [];
                this.setStatus(`Catálogo embutido indisponível: ${error.message}`, "warn");
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
                await this.refreshSmallWindowPreview();
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

        async refreshSmallWindowPreview() {
            if (!this.editor) {
                return;
            }
            const timeFormat = this.editor.small_window?.time_format || "%H:%M";
            try {
                const response = await fetch(
                    `/api/small-window/preview?${new URLSearchParams([
                        ["time_format", timeFormat],
                        ...((this.editor.small_window?.metrics_items || []).map((item) => ["metrics_items", item])),
                    ]).toString()}`,
                );
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.detail || payload.error || "Falha ao atualizar a prévia");
                }
                this.smallWindowPreview = {
                    time_text: payload.time_text || "--:--",
                    cpu_percent: Number(payload.cpu_percent) || 0,
                    mem_percent: Number(payload.mem_percent) || 0,
                    gpu_percent: Number(payload.gpu_percent) || 0,
                    metrics: Array.isArray(payload.metrics) ? payload.metrics : [],
                };
            } catch (_error) {
                this.smallWindowPreview = {
                    ...this.smallWindowPreview,
                    time_text: this.smallWindowPreview.time_text || "--:--",
                };
            }
        },

        normalizeEditor(payload) {
            const editor = JSON.parse(JSON.stringify(payload));
            editor.pages = (editor.pages || []).map((page) => ({
                name: page.name,
                buttons: (page.buttons || [])
                    .map((button) => this.normalizeButton(button))
                    .filter((button) => this.isEditableSlot(button.index)),
            }));
            editor.fixed_buttons = (editor.fixed_buttons || [])
                .map((button) => this.normalizeButton(button))
                .filter((button) => this.isEditableSlot(button.index));
            editor.small_window = editor.small_window || {
                enabled: false,
                interval_s: 2.0,
                time_format: "%H:%M",
                show_metrics: true,
                rotate_every_s: null,
                background_color: "#000000",
                metrics_items: [],
            };
            editor.small_window.show_metrics = editor.small_window.show_metrics !== false;
            editor.small_window.rotate_every_s = this.parseOptionalNumber(editor.small_window.rotate_every_s);
            editor.small_window.background_color = editor.small_window.background_color || "#000000";
            editor.small_window.metrics_items = Array.isArray(editor.small_window.metrics_items)
                ? editor.small_window.metrics_items.slice(0, 3)
                : [];
            return editor;
        },

        parseOptionalNumber(value) {
            if (value === null || value === undefined || value === "") {
                return null;
            }
            const parsed = Number(value);
            return Number.isFinite(parsed) ? parsed : null;
        },

        formatSeconds(value) {
            const parsed = Number(value);
            if (!Number.isFinite(parsed)) {
                return "";
            }
            return Number.isInteger(parsed)
                ? String(parsed)
                : parsed.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
        },

        normalizeButton(button) {
            const infoWindow = this.isInfoWindowSlot(button.index);
            return {
                index: button.index,
                label: infoWindow ? "" : (button.label || ""),
                icon_path: infoWindow ? "" : (button.icon_path || ""),
                preview_url: infoWindow ? "" : (button.preview_url || this.assetUrl(button.icon_path)),
                action: { ...emptyAction(), ...(button.action || {}) },
                text_style: this.normalizeTextStyle(button.text_style),
            };
        },

        normalizeTextStyle(style) {
            return { ...emptyTextStyle(), ...(style || {}) };
        },

        assetUrl(path) {
            return path ? `/api/asset?path=${encodeURIComponent(path)}` : "";
        },

        isInfoWindowSlot(index) {
            return index === INFO_WINDOW_INDEX;
        },

        isEditableSlot(index) {
            return DECK_LAYOUT.some((slot) => slot.index === index);
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
            this.showBuiltinIconBrowser = false;
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
                text_style: this.normalizeTextStyle(source.text_style),
            };
        },

        normalizeActionFromForm() {
            const action = { ...emptyAction(), ...(this.buttonForm?.action || {}) };
            switch (action.type) {
            case "shell":
                return { ...emptyAction(), type: "shell", cmd: action.cmd || "" };
            case "shortcut":
                return { ...emptyAction(), type: "shortcut", keys: action.keys || "" };
            case "predefined_command":
                return {
                    ...emptyAction(),
                    type: "predefined_command",
                    command_id: action.command_id || "",
                };
            case "url":
                return { ...emptyAction(), type: "url", url: action.url || "" };
            case "switch_page":
                return { ...emptyAction(), type: "switch_page", page: action.page || "" };
            default:
                return emptyAction();
            }
        },

        buildStateButtonFromForm() {
            const actionOnly = this.isInfoWindowSlot(this.selectedIndex);
            return {
                index: this.selectedIndex,
                label: actionOnly ? "" : (this.buttonForm.label || ""),
                icon_path: actionOnly ? "" : (this.buttonForm.icon_path || ""),
                preview_url: actionOnly ? "" : (this.buttonForm.preview_url || this.assetUrl(this.buttonForm.icon_path)),
                action: this.normalizeActionFromForm(),
                text_style: actionOnly
                    ? emptyTextStyle()
                    : this.normalizeTextStyle(this.buttonForm.text_style),
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

            const persistInfoWindowFixedPlaceholder = (
                this.isInfoWindowSlot(this.selectedIndex)
                && Boolean(this.buttonForm.fixed)
            );

            if (this.isButtonMeaningful(nextButton) || persistInfoWindowFixedPlaceholder) {
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

        toggleBuiltinIconBrowser() {
            this.showBuiltinIconBrowser = !this.showBuiltinIconBrowser;
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

        async useBuiltinIcon(icon) {
            this.busy = true;
            try {
                const response = await fetch("/api/builtin-assets/import", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ asset_id: icon.asset_id }),
                });
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.detail || payload.error || "Falha ao importar ícone embutido");
                }
                this.buttonForm.icon_path = payload.path;
                this.buttonForm.preview_url = payload.preview_url;
                this.syncSelectedButton();
                this.showBuiltinIconBrowser = false;
                this.setStatus(`Ícone embutido aplicado: ${icon.name}`, "ok");
            } catch (error) {
                this.setStatus(`Falha ao importar catálogo: ${error.message}`, "err");
            } finally {
                this.busy = false;
            }
        },

        serializeButton(button) {
            return {
                index: button.index,
                label: button.label || "",
                icon_path: button.icon_path || null,
                action: { ...emptyAction(), ...(button.action || {}) },
                text_style: this.normalizeTextStyle(button.text_style),
            };
        },

        hasTextOnlyPreview(button) {
            return Boolean(
                button
                && !button.preview_url
                && !(button.icon_path || "").trim()
                && (button.label || "").trim(),
            );
        },

        tileStyleFor(style) {
            const normalized = this.normalizeTextStyle(style);
            return {
                background: normalized.background_color,
            };
        },

        textStyleFor(style, scale = 0.42) {
            const normalized = this.normalizeTextStyle(style);
            return {
                color: normalized.text_color,
                fontFamily: `"${normalized.font_family}", var(--font-sans)`,
                fontSize: `${Math.max(12, Math.round(normalized.font_size * scale))}px`,
                fontWeight: normalized.bold ? "700" : "500",
                fontStyle: normalized.italic ? "italic" : "normal",
                textDecoration: normalized.underline ? "underline" : "none",
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
                    rotate_every_s: this.parseOptionalNumber(this.editor.small_window.rotate_every_s),
                    background_color: this.editor.small_window.background_color || "#000000",
                    metrics_items: (this.editor.small_window.metrics_items || []).slice(0, 3),
                },
                save_firmware_bundle: Boolean(this.saveFirmwareBundle),
            };
        },

        toggleSmallWindowMetric(metric) {
            const current = this.editor.small_window.metrics_items || [];
            if (current.includes(metric)) {
                this.editor.small_window.metrics_items = current.filter((item) => item !== metric);
            } else if (current.length < 3) {
                this.editor.small_window.metrics_items = [...current, metric];
            }
            this.dirty = true;
            void this.refreshSmallWindowPreview();
        },

        smallWindowMetricSelected(metric) {
            return (this.editor.small_window.metrics_items || []).includes(metric);
        },

        smallWindowMetricDisabled(metric) {
            return !this.smallWindowMetricSelected(metric)
                && (this.editor.small_window.metrics_items || []).length >= 3;
        },

        smallWindowPreviewStyle() {
            return {
                background: this.editor?.small_window?.background_color || "#000000",
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
            this.setStatus("Deck resetado. Clique em Salvar no deck para aplicar.", "warn");
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
                await this.refreshSmallWindowPreview();
                const savedItems = [
                    this.savedArtifactLabel(payload.versioned_config_path),
                    this.savedArtifactLabel(payload.saved_firmware_bundle_path),
                ].filter(Boolean);
                this.setStatus(
                    savedItems.length
                        ? `Salvo às ${new Date().toLocaleTimeString()} · ${savedItems.join(" · ")}`
                        : `Salvo às ${new Date().toLocaleTimeString()}`,
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

        savedArtifactLabel(path) {
            if (!path) {
                return "";
            }
            const parts = String(path).split("/").filter(Boolean);
            const tail = parts[parts.length - 1] || path;
            return tail.endsWith(".zip") ? `ZIP ${tail}` : `snapshot ${tail}`;
        },

        slotStyle(slot) {
            return `grid-column: ${slot.column} / span ${slot.span}; grid-row: ${slot.row};`;
        },

        buttonClasses(slot) {
            return {
                selected: slot.index === this.selectedIndex,
                fixed: slot.fixed,
                empty: slot.empty,
                info: this.isInfoWindowSlot(slot.index),
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
                if (this.isInfoWindowSlot(slot.index)) {
                    return {
                        ...slot,
                        fixed: Boolean(fixedButton),
                        empty: !this.editor?.small_window?.enabled,
                        label: "Small window",
                        preview_url: "",
                        textOnly: false,
                        text_style: emptyTextStyle(),
                        actionLabel: button
                            ? this.actionLabel(button?.action?.type || "none")
                            : this.smallWindowSummary,
                        placeholder: "Info window",
                    };
                }
                return {
                    ...slot,
                    fixed: Boolean(fixedButton),
                    empty: !button,
                    label: button?.label || "",
                    preview_url: button?.preview_url || this.assetUrl(button?.icon_path),
                    textOnly: this.hasTextOnlyPreview(button),
                    text_style: this.normalizeTextStyle(button?.text_style),
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

        get filteredBuiltinIcons() {
            const query = (this.builtinIconQuery || "").trim().toLowerCase();
            const style = this.builtinIconStyle || "all";
            return (this.builtinIcons || [])
                .filter((icon) => style === "all" || icon.style === style)
                .filter((icon) => {
                    if (!query) {
                        return true;
                    }
                    const haystack = [icon.name, icon.style, icon.family, ...(icon.search_terms || [])]
                        .join(" ")
                        .toLowerCase();
                    return haystack.includes(query);
                })
                .slice(0, 120);
        },

        get builtinIconSummary() {
            const total = (this.builtinIcons || []).length;
            const visible = this.filteredBuiltinIcons.length;
            return `${visible} de ${total} assets embutidos`;
        },

        get currentTextOnlyPreview() {
            return this.hasTextOnlyPreview(this.buttonForm);
        },

        get showTextStyleControls() {
            return Boolean(
                this.buttonForm
                && this.selectedIndex !== INFO_WINDOW_INDEX
                && !(this.buttonForm.icon_path || "").trim(),
            );
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
            if (this.isInfoWindowSlot(slot.index)) {
                return "Info window · ação ao toque";
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
            if (this.smallWindowAlternates) {
                const seconds = this.formatSeconds(this.editor.small_window.rotate_every_s);
                return this.usesCustomSmallWindowMetrics
                    ? `Relógio ${seconds}s / métricas ${seconds}s`
                    : `Relógio ${seconds}s / estatísticas ${seconds}s`;
            }
            return this.editor.small_window.show_metrics === false
                ? "Somente relógio"
                : this.usesCustomSmallWindowMetrics
                    ? "Métricas customizadas"
                    : "Estatísticas nativas";
        },

        get smallWindowAlternates() {
            return Boolean(
                this.editor?.small_window?.enabled
                && this.editor.small_window.show_metrics !== false
                && this.parseOptionalNumber(this.editor.small_window.rotate_every_s) !== null,
            );
        },

        get smallWindowRotateLabel() {
            return this.formatSeconds(this.editor?.small_window?.rotate_every_s);
        },

        get smallWindowTimeLabel() {
            return this.smallWindowPreview.time_text || "--:--";
        },

        get usesCustomSmallWindowMetrics() {
            return Boolean((this.editor?.small_window?.metrics_items || []).length);
        },

        get currentTextTileStyle() {
            return this.tileStyleFor(this.buttonForm?.text_style);
        },

        get currentTextLabelStyle() {
            return this.textStyleFor(this.buttonForm?.text_style, 0.72);
        },
    };
};
