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
const ICON_RENDER_SIZE = 196;
const ICON_RENDER_PADDING = 14;

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

const PREDEFINED_CATEGORY_LABELS = Object.freeze({
    audio: "Áudio",
    display: "Tela",
    input: "Entrada",
    navigation: "Navegação",
    window: "Janela",
    workspace: "Workspaces",
    settings: "Configurações",
    system: "Sistema",
    launchers: "Aplicativos",
});

const SHORTCUT_MODIFIERS = Object.freeze([
    { value: "ctrl", label: "Ctrl" },
    { value: "alt", label: "Alt" },
    { value: "shift", label: "Shift" },
    { value: "super", label: "Super" },
]);

const SHORTCUT_KEY_GROUPS = Object.freeze([
    {
        label: "Setas",
        keys: [
            { value: "Left", label: "←" },
            { value: "Right", label: "→" },
            { value: "Up", label: "↑" },
            { value: "Down", label: "↓" },
        ],
    },
    {
        label: "Navegação",
        keys: [
            { value: "Home", label: "Home" },
            { value: "End", label: "End" },
            { value: "Page_Up", label: "PgUp" },
            { value: "Page_Down", label: "PgDn" },
            { value: "Tab", label: "Tab" },
            { value: "Escape", label: "Esc" },
            { value: "Insert", label: "Ins" },
            { value: "Delete", label: "Del" },
        ],
    },
    {
        label: "Edição",
        keys: [
            { value: "Return", label: "Enter" },
            { value: "space", label: "Espaço" },
            { value: "BackSpace", label: "Backspace" },
            { value: "slash", label: "/" },
            { value: "period", label: "." },
            { value: "comma", label: "," },
        ],
    },
    {
        label: "Funções",
        keys: [
            { value: "F1", label: "F1" },
            { value: "F2", label: "F2" },
            { value: "F3", label: "F3" },
            { value: "F4", label: "F4" },
            { value: "F5", label: "F5" },
            { value: "F6", label: "F6" },
            { value: "F7", label: "F7" },
            { value: "F8", label: "F8" },
            { value: "F9", label: "F9" },
            { value: "F10", label: "F10" },
            { value: "F11", label: "F11" },
            { value: "F12", label: "F12" },
        ],
    },
    {
        label: "Mídia",
        keys: [
            { value: "XF86AudioMute", label: "Mute" },
            { value: "XF86AudioRaiseVolume", label: "Vol+" },
            { value: "XF86AudioLowerVolume", label: "Vol-" },
            { value: "XF86AudioPlay", label: "Play/Pause" },
            { value: "XF86AudioNext", label: "Próxima faixa" },
            { value: "XF86AudioPrev", label: "Faixa anterior" },
            { value: "XF86AudioMicMute", label: "Mic mute" },
            { value: "XF86MonBrightnessUp", label: "Brilho+" },
            { value: "XF86MonBrightnessDown", label: "Brilho-" },
        ],
    },
]);

const ICON_LIBRARY_OPTIONS = Object.freeze([
    {
        id: "fa-solid",
        label: "Font Awesome 5",
        icons: [
            { iconify: "fa-solid:terminal", label: "Terminal", keywords: ["shell", "console"] },
            { iconify: "fa-solid:folder-open", label: "Pasta", keywords: ["files", "nautilus"] },
            { iconify: "fa-solid:play", label: "Play", keywords: ["media"] },
            { iconify: "fa-solid:pause", label: "Pause", keywords: ["media"] },
            { iconify: "fa-solid:stop", label: "Stop", keywords: ["media"] },
            { iconify: "fa-solid:step-forward", label: "Próxima faixa", keywords: ["media", "next"] },
            { iconify: "fa-solid:step-backward", label: "Faixa anterior", keywords: ["media", "prev"] },
            { iconify: "fa-solid:volume-up", label: "Volume alto", keywords: ["audio", "speaker"] },
            { iconify: "fa-solid:volume-down", label: "Volume baixo", keywords: ["audio", "speaker"] },
            { iconify: "fa-solid:volume-mute", label: "Mudo", keywords: ["audio", "mute"] },
            { iconify: "fa-solid:microphone", label: "Microfone", keywords: ["audio", "mic"] },
            { iconify: "fa-solid:microphone-slash", label: "Microfone mudo", keywords: ["audio", "mic", "mute"] },
            { iconify: "fa-solid:sun", label: "Sol", keywords: ["brightness", "light"] },
            { iconify: "fa-solid:moon", label: "Lua", keywords: ["night", "dark"] },
            { iconify: "fa-solid:keyboard", label: "Teclado", keywords: ["input", "layout"] },
            { iconify: "fa-solid:globe", label: "Globo", keywords: ["web", "browser"] },
            { iconify: "fa-solid:wifi", label: "Wi-Fi", keywords: ["network"] },
            { iconify: "fa-solid:cog", label: "Configurações", keywords: ["settings"] },
            { iconify: "fa-solid:power-off", label: "Energia", keywords: ["power", "shutdown"] },
            { iconify: "fa-solid:lock", label: "Cadeado", keywords: ["lock"] },
            { iconify: "fa-solid:search", label: "Busca", keywords: ["search"] },
            { iconify: "fa-solid:bell", label: "Notificação", keywords: ["notification"] },
            { iconify: "fa-solid:camera", label: "Câmera", keywords: ["photo", "capture"] },
            { iconify: "fa-solid:image", label: "Imagem", keywords: ["picture"] },
            { iconify: "fa-solid:video", label: "Vídeo", keywords: ["recording"] },
            { iconify: "fa-solid:music", label: "Música", keywords: ["audio", "media"] },
            { iconify: "fa-solid:code", label: "Código", keywords: ["dev", "programming"] },
            { iconify: "fa-solid:bug", label: "Bug", keywords: ["debug"] },
            { iconify: "fa-solid:rocket", label: "Foguete", keywords: ["launch"] },
            { iconify: "fa-solid:save", label: "Salvar", keywords: ["disk"] },
            { iconify: "fa-solid:trash", label: "Lixeira", keywords: ["delete"] },
            { iconify: "fa-solid:cloud-upload-alt", label: "Upload", keywords: ["cloud"] },
            { iconify: "fa-solid:cloud-download-alt", label: "Download", keywords: ["cloud"] },
            { iconify: "fa-solid:home", label: "Home", keywords: ["house"] },
            { iconify: "fa-solid:desktop", label: "Desktop", keywords: ["monitor", "workspace"] },
            { iconify: "fa-solid:external-link-alt", label: "Abrir externo", keywords: ["link", "open"] },
        ],
    },
    {
        id: "mdi",
        label: "Material Design Icons",
        icons: [
            { iconify: "mdi:console", label: "Console", keywords: ["terminal", "shell"] },
            { iconify: "mdi:folder-open-outline", label: "Pasta", keywords: ["files", "nautilus"] },
            { iconify: "mdi:play-circle-outline", label: "Play", keywords: ["media"] },
            { iconify: "mdi:pause-circle-outline", label: "Pause", keywords: ["media"] },
            { iconify: "mdi:stop-circle-outline", label: "Stop", keywords: ["media"] },
            { iconify: "mdi:skip-next-circle-outline", label: "Próxima faixa", keywords: ["media", "next"] },
            { iconify: "mdi:skip-previous-circle-outline", label: "Faixa anterior", keywords: ["media", "prev"] },
            { iconify: "mdi:volume-high", label: "Volume alto", keywords: ["audio"] },
            { iconify: "mdi:volume-medium", label: "Volume baixo", keywords: ["audio"] },
            { iconify: "mdi:volume-off", label: "Mudo", keywords: ["audio", "mute"] },
            { iconify: "mdi:microphone", label: "Microfone", keywords: ["audio", "mic"] },
            { iconify: "mdi:microphone-off", label: "Microfone mudo", keywords: ["audio", "mic", "mute"] },
            { iconify: "mdi:white-balance-sunny", label: "Sol", keywords: ["brightness", "light"] },
            { iconify: "mdi:weather-night", label: "Lua", keywords: ["night", "dark"] },
            { iconify: "mdi:keyboard-outline", label: "Teclado", keywords: ["input", "layout"] },
            { iconify: "mdi:web", label: "Web", keywords: ["browser"] },
            { iconify: "mdi:wifi", label: "Wi-Fi", keywords: ["network"] },
            { iconify: "mdi:cog-outline", label: "Configurações", keywords: ["settings"] },
            { iconify: "mdi:power", label: "Energia", keywords: ["power", "shutdown"] },
            { iconify: "mdi:lock-outline", label: "Cadeado", keywords: ["lock"] },
            { iconify: "mdi:magnify", label: "Busca", keywords: ["search"] },
            { iconify: "mdi:bell-outline", label: "Notificação", keywords: ["notification"] },
            { iconify: "mdi:camera-outline", label: "Câmera", keywords: ["photo", "capture"] },
            { iconify: "mdi:image-outline", label: "Imagem", keywords: ["picture"] },
            { iconify: "mdi:video-outline", label: "Vídeo", keywords: ["recording"] },
            { iconify: "mdi:music-note", label: "Música", keywords: ["audio", "media"] },
            { iconify: "mdi:code-tags", label: "Código", keywords: ["dev", "programming"] },
            { iconify: "mdi:bug-outline", label: "Bug", keywords: ["debug"] },
            { iconify: "mdi:rocket-launch-outline", label: "Foguete", keywords: ["launch"] },
            { iconify: "mdi:content-save-outline", label: "Salvar", keywords: ["disk"] },
            { iconify: "mdi:trash-can-outline", label: "Lixeira", keywords: ["delete"] },
            { iconify: "mdi:cloud-upload-outline", label: "Upload", keywords: ["cloud"] },
            { iconify: "mdi:cloud-download-outline", label: "Download", keywords: ["cloud"] },
            { iconify: "mdi:home-outline", label: "Home", keywords: ["house"] },
            { iconify: "mdi:monitor-dashboard", label: "Desktop", keywords: ["monitor", "workspace"] },
            { iconify: "mdi:open-in-new", label: "Abrir externo", keywords: ["link", "open"] },
        ],
    },
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

function emptyShortcutDraft() {
    return {
        modifiers: [],
        key: "",
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
        },
    };
}

window.editorApp = function editorApp() {
    return {
        health: { ok: false, version: "", config_path: "", devices_found: 0 },
        editor: null,
        predefinedCommands: [],
        saveFirmwareBundle: false,
        smallWindowPreview: {
            time_text: "--:--",
            cpu_percent: 0,
            mem_percent: 0,
            gpu_percent: 0,
        },
        status: "",
        statusClass: "",
        validationError: "",
        dirty: false,
        busy: false,
        selectedPage: "",
        selectedIndex: 0,
        buttonForm: null,
        newPageName: "",
        predefinedCommandQuery: "",
        iconModalOpen: false,
        iconLibrary: ICON_LIBRARY_OPTIONS[0].id,
        iconSearch: "",
        shortcutModalOpen: false,
        shortcutDraft: emptyShortcutDraft(),
        fontOptions: FONT_OPTIONS,
        iconLibraryOptions: ICON_LIBRARY_OPTIONS,
        shortcutModifiers: SHORTCUT_MODIFIERS,
        shortcutKeyGroups: SHORTCUT_KEY_GROUPS,

        async init() {
            await Promise.all([
                this.refreshHealth(),
                this.loadPredefinedCommands(),
            ]);
            await this.loadEditor();
            await this.refreshSmallWindowPreview();
            setInterval(() => {
                void this.refreshHealth();
            }, 5000);
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

        async loadPredefinedCommands() {
            try {
                const response = await fetch("/api/catalog/predefined-commands");
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.detail || payload.error || "Falha ao carregar comandos pré-definidos");
                }
                this.predefinedCommands = payload;
            } catch (_error) {
                this.predefinedCommands = [];
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
                    `/api/small-window/preview?time_format=${encodeURIComponent(timeFormat)}`,
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
            editor.small_window = {
                enabled: true,
                interval_s: 2.0,
                time_format: "%H:%M",
                show_metrics: false,
                rotate_every_s: null,
                ...(editor.small_window || {}),
            };
            editor.small_window.enabled = editor.small_window.enabled !== false;
            editor.small_window.show_metrics = editor.small_window.show_metrics === true;
            editor.small_window.rotate_every_s = this.parseOptionalNumber(editor.small_window.rotate_every_s);
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

        iconChoiceUrl(choice) {
            return `https://api.iconify.design/${choice.iconify}.svg?color=%23F8FAFC`;
        },

        predefinedCategoryLabel(category) {
            return PREDEFINED_CATEGORY_LABELS[category] || category;
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

        slotTooltip(slot) {
            const label = String(slot?.tooltipLabel || "").trim();
            const action = String(slot?.tooltipAction || "").trim();
            return [label, action].filter(Boolean).join(" · ");
        },

        selectPage(name) {
            this.selectedPage = name;
            this.selectSlot(this.selectedIndex);
        },

        selectSlot(index) {
            this.selectedIndex = index;
            this.buttonForm = this.formForIndex(index);
            this.validationError = "";
            this.predefinedCommandQuery = "";
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

        async sendAssetBlob(blob, filename) {
            const form = new FormData();
            form.append("file", blob, filename);
            const response = await fetch("/api/assets", {
                method: "POST",
                body: form,
            });
            const payload = await response.json();
            if (!response.ok) {
                throw new Error(payload.detail || payload.error || "Falha no upload da imagem");
            }
            return payload;
        },

        applyAssetPayload(payload, statusText) {
            this.buttonForm.icon_path = payload.path;
            this.buttonForm.preview_url = payload.preview_url;
            this.syncSelectedButton();
            this.setStatus(statusText, "ok");
        },

        async uploadIcon(event) {
            const file = event.target.files?.[0];
            if (!file) {
                return;
            }
            this.busy = true;
            try {
                const payload = await this.sendAssetBlob(file, file.name || "button-icon.png");
                this.applyAssetPayload(payload, `Imagem enviada: ${file.name}`);
            } catch (error) {
                this.setStatus(`Falha no upload: ${error.message}`, "err");
            } finally {
                this.busy = false;
                event.target.value = "";
            }
        },

        openIconModal() {
            this.iconModalOpen = true;
            this.iconSearch = "";
        },

        closeIconModal() {
            this.iconModalOpen = false;
        },

        async fetchIconSvg(choice) {
            const response = await fetch(this.iconChoiceUrl(choice));
            if (!response.ok) {
                throw new Error("Não foi possível baixar o ícone selecionado");
            }
            const svgMarkup = await response.text();
            return svgMarkup.includes("color=")
                ? svgMarkup
                : svgMarkup.replace("<svg", '<svg color="#F8FAFC"');
        },

        async renderSvgToPngBlob(svgMarkup) {
            const svgBlob = new Blob([svgMarkup], { type: "image/svg+xml;charset=utf-8" });
            const objectUrl = URL.createObjectURL(svgBlob);
            try {
                const image = await new Promise((resolve, reject) => {
                    const img = new Image();
                    img.onload = () => resolve(img);
                    img.onerror = () => reject(new Error("Falha ao rasterizar o ícone"));
                    img.src = objectUrl;
                });
                const canvas = document.createElement("canvas");
                canvas.width = ICON_RENDER_SIZE;
                canvas.height = ICON_RENDER_SIZE;
                const context = canvas.getContext("2d");
                if (!context) {
                    throw new Error("Canvas indisponível neste navegador");
                }
                const maxSize = ICON_RENDER_SIZE - (ICON_RENDER_PADDING * 2);
                const width = image.naturalWidth || ICON_RENDER_SIZE;
                const height = image.naturalHeight || ICON_RENDER_SIZE;
                const scale = Math.min(maxSize / width, maxSize / height);
                const drawWidth = Math.max(1, Math.round(width * scale));
                const drawHeight = Math.max(1, Math.round(height * scale));
                const x = Math.round((ICON_RENDER_SIZE - drawWidth) / 2);
                const y = Math.round((ICON_RENDER_SIZE - drawHeight) / 2);
                context.clearRect(0, 0, ICON_RENDER_SIZE, ICON_RENDER_SIZE);
                context.drawImage(image, x, y, drawWidth, drawHeight);
                return await new Promise((resolve, reject) => {
                    canvas.toBlob((blob) => {
                        if (blob) {
                            resolve(blob);
                            return;
                        }
                        reject(new Error("Falha ao gerar PNG do ícone"));
                    }, "image/png");
                });
            } finally {
                URL.revokeObjectURL(objectUrl);
            }
        },

        async chooseLibraryIcon(choice) {
            this.busy = true;
            try {
                const svgMarkup = await this.fetchIconSvg(choice);
                const pngBlob = await this.renderSvgToPngBlob(svgMarkup);
                const filename = `${choice.iconify.replace(/[:/]/g, "-")}.png`;
                const payload = await this.sendAssetBlob(pngBlob, filename);
                this.applyAssetPayload(payload, `Ícone aplicado: ${choice.label}`);
                this.closeIconModal();
            } catch (error) {
                this.setStatus(`Falha ao aplicar ícone: ${error.message}`, "err");
            } finally {
                this.busy = false;
            }
        },

        normalizeShortcutDraft(keys) {
            const modifierValues = new Set(SHORTCUT_MODIFIERS.map((modifier) => modifier.value));
            const draft = emptyShortcutDraft();
            const tokens = String(keys || "")
                .split("+")
                .map((token) => token.trim())
                .filter(Boolean);
            for (const token of tokens) {
                const normalized = token.toLowerCase();
                const mapped = normalized === "control"
                    ? "ctrl"
                    : normalized === "win"
                    ? "super"
                    : normalized;
                if (modifierValues.has(mapped)) {
                    if (!draft.modifiers.includes(mapped)) {
                        draft.modifiers.push(mapped);
                    }
                    continue;
                }
                draft.key = token;
            }
            return draft;
        },

        toggleShortcutModifier(value) {
            if (this.shortcutDraft.modifiers.includes(value)) {
                this.shortcutDraft.modifiers = this.shortcutDraft.modifiers.filter((item) => item !== value);
                return;
            }
            this.shortcutDraft.modifiers = [...this.shortcutDraft.modifiers, value];
        },

        setShortcutKey(value) {
            this.shortcutDraft.key = value;
        },

        openShortcutModal() {
            this.shortcutDraft = this.normalizeShortcutDraft(this.buttonForm?.action?.keys || "");
            this.shortcutModalOpen = true;
        },

        closeShortcutModal() {
            this.shortcutModalOpen = false;
        },

        composeShortcutKeys(draft = this.shortcutDraft) {
            const modifierOrder = SHORTCUT_MODIFIERS.map((modifier) => modifier.value);
            const orderedModifiers = modifierOrder.filter((value) => draft.modifiers.includes(value));
            return [...orderedModifiers, draft.key].filter(Boolean).join("+");
        },

        applyShortcutSelection() {
            const keys = this.composeShortcutKeys();
            if (!keys) {
                this.setStatus("Escolha uma tecla para montar o atalho", "err");
                return;
            }
            this.buttonForm.action.keys = keys;
            this.syncSelectedButton();
            this.closeShortcutModal();
            this.setStatus(`Atalho aplicado: ${keys}`, "ok");
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
                    show_metrics: this.editor.small_window.show_metrics === true,
                    rotate_every_s: this.parseOptionalNumber(this.editor.small_window.rotate_every_s),
                },
                save_firmware_bundle: Boolean(this.saveFirmwareBundle),
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
                    const tooltipLabel = "Small window";
                    const tooltipAction = button
                        ? this.actionLabel(button?.action?.type || "none")
                        : this.smallWindowSummary;
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
                        tooltipLabel,
                        tooltipAction,
                        placeholder: "Info window",
                    };
                }
                const placeholder = slot.span === 2
                    ? `Botão ${slot.index + 1} · 2x1`
                    : `Botão ${slot.index + 1}`;
                return {
                    ...slot,
                    fixed: Boolean(fixedButton),
                    empty: !button,
                    label: button?.label || "",
                    preview_url: button?.preview_url || this.assetUrl(button?.icon_path),
                    textOnly: this.hasTextOnlyPreview(button),
                    text_style: this.normalizeTextStyle(button?.text_style),
                    actionLabel: this.actionLabel(button?.action?.type || "none"),
                    tooltipLabel: (button?.label || "").trim() || `Botão ${slot.index + 1}`,
                    tooltipAction: this.actionLabel(button?.action?.type || "none"),
                    placeholder,
                };
            });
        },

        get currentPreviewUrl() {
            return this.buttonForm?.preview_url || this.assetUrl(this.buttonForm?.icon_path);
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

        get predefinedCommandOptions() {
            const search = this.predefinedCommandQuery.trim().toLowerCase();
            if (!search) {
                return this.predefinedCommands;
            }
            return this.predefinedCommands.filter((command) => {
                const haystack = [
                    command.label,
                    command.description,
                    command.category,
                    command.preview,
                    ...(command.keywords || []),
                ]
                    .join(" ")
                    .toLowerCase();
                return haystack.includes(search);
            });
        },

        get selectedPredefinedCommand() {
            const commandId = this.buttonForm?.action?.command_id || "";
            return this.predefinedCommands.find((command) => command.command_id === commandId) || null;
        },

        get currentIconLibrary() {
            return this.iconLibraryOptions.find((library) => library.id === this.iconLibrary)
                || this.iconLibraryOptions[0];
        },

        get filteredIconChoices() {
            const search = this.iconSearch.trim().toLowerCase();
            const icons = this.currentIconLibrary?.icons || [];
            if (!search) {
                return icons;
            }
            return icons.filter((choice) => {
                const haystack = [choice.label, choice.iconify, ...(choice.keywords || [])]
                    .join(" ")
                    .toLowerCase();
                return haystack.includes(search);
            });
        },

        get smallWindowSummary() {
            if (!this.editor?.small_window?.enabled) {
                return "Desligado";
            }
            if (this.smallWindowAlternates) {
                const seconds = this.formatSeconds(this.editor.small_window.rotate_every_s);
                return `Relógio ${seconds}s / estatísticas ${seconds}s`;
            }
            return this.editor.small_window.show_metrics === true
                ? "Estatísticas"
                : "Somente relógio";
        },

        get smallWindowAlternates() {
            return Boolean(
                this.editor?.small_window?.enabled
                && this.editor.small_window.show_metrics === true
                && this.parseOptionalNumber(this.editor.small_window.rotate_every_s) !== null,
            );
        },

        get smallWindowRotateLabel() {
            return this.formatSeconds(this.editor?.small_window?.rotate_every_s);
        },

        get smallWindowTimeLabel() {
            return this.smallWindowPreview.time_text || "--:--";
        },

        get currentTextTileStyle() {
            return this.tileStyleFor(this.buttonForm?.text_style);
        },

        get currentTextLabelStyle() {
            return this.textStyleFor(this.buttonForm?.text_style, 0.72);
        },

        get shortcutSelectionText() {
            return this.composeShortcutKeys() || "Selecione uma combinação";
        },
    };
};