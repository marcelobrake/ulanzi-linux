"""Catalog of common GNOME desktop actions exposed in the web editor.

These commands stay as data so both the YAML loader and the web API can
validate them, while the runner resolves each catalog entry to an existing
shell / shortcut / URL action at execution time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ulanzi_linux.domain.button_config import ShellAction, ShortcutAction, UrlAction

ResolvedPredefinedAction = ShellAction | ShortcutAction | UrlAction
PredefinedCategory = Literal[
    "audio",
    "display",
    "input",
    "navigation",
    "window",
    "workspace",
    "settings",
    "system",
    "launchers",
]


@dataclass(frozen=True, slots=True)
class PredefinedCommandDefinition:
    command_id: str
    label: str
    description: str
    category: PredefinedCategory
    action: ResolvedPredefinedAction
    keywords: tuple[str, ...] = ()


PREDEFINED_COMMANDS: tuple[PredefinedCommandDefinition, ...] = (
    PredefinedCommandDefinition(
        command_id="audio_mute",
        label="Alternar mudo",
        description="Liga ou desliga o mudo do áudio do sistema.",
        category="audio",
        action=ShortcutAction(type="shortcut", keys="XF86AudioMute"),
        keywords=("mute", "som", "volume"),
    ),
    PredefinedCommandDefinition(
        command_id="audio_volume_up",
        label="Aumentar volume",
        description="Aumenta o volume de saída.",
        category="audio",
        action=ShortcutAction(type="shortcut", keys="XF86AudioRaiseVolume"),
        keywords=("vol+", "som", "speaker"),
    ),
    PredefinedCommandDefinition(
        command_id="audio_volume_down",
        label="Diminuir volume",
        description="Diminui o volume de saída.",
        category="audio",
        action=ShortcutAction(type="shortcut", keys="XF86AudioLowerVolume"),
        keywords=("vol-", "som", "speaker"),
    ),
    PredefinedCommandDefinition(
        command_id="audio_mic_mute",
        label="Alternar mudo do microfone",
        description="Liga ou desliga o mudo do microfone.",
        category="audio",
        action=ShortcutAction(type="shortcut", keys="XF86AudioMicMute"),
        keywords=("microfone", "mute"),
    ),
    PredefinedCommandDefinition(
        command_id="media_play_pause",
        label="Play / Pause",
        description="Alterna reprodução e pausa da mídia atual.",
        category="audio",
        action=ShortcutAction(type="shortcut", keys="XF86AudioPlay"),
        keywords=("mídia", "player"),
    ),
    PredefinedCommandDefinition(
        command_id="media_stop",
        label="Parar mídia",
        description="Para a reprodução atual.",
        category="audio",
        action=ShortcutAction(type="shortcut", keys="XF86AudioStop"),
        keywords=("mídia", "player"),
    ),
    PredefinedCommandDefinition(
        command_id="media_next",
        label="Próxima faixa",
        description="Avança para a próxima faixa.",
        category="audio",
        action=ShortcutAction(type="shortcut", keys="XF86AudioNext"),
        keywords=("mídia", "player"),
    ),
    PredefinedCommandDefinition(
        command_id="media_previous",
        label="Faixa anterior",
        description="Volta para a faixa anterior.",
        category="audio",
        action=ShortcutAction(type="shortcut", keys="XF86AudioPrev"),
        keywords=("mídia", "player"),
    ),
    PredefinedCommandDefinition(
        command_id="display_brightness_up",
        label="Aumentar brilho",
        description="Aumenta o brilho da tela.",
        category="display",
        action=ShortcutAction(type="shortcut", keys="XF86MonBrightnessUp"),
        keywords=("brilho", "tela"),
    ),
    PredefinedCommandDefinition(
        command_id="display_brightness_down",
        label="Diminuir brilho",
        description="Diminui o brilho da tela.",
        category="display",
        action=ShortcutAction(type="shortcut", keys="XF86MonBrightnessDown"),
        keywords=("brilho", "tela"),
    ),
    PredefinedCommandDefinition(
        command_id="display_screenshot_full",
        label="Capturar tela inteira",
        description="Tira um screenshot da tela inteira.",
        category="display",
        action=ShortcutAction(type="shortcut", keys="Print"),
        keywords=("screenshot", "captura"),
    ),
    PredefinedCommandDefinition(
        command_id="display_screenshot_selection",
        label="Capturar área",
        description="Tira um screenshot de uma área selecionada.",
        category="display",
        action=ShortcutAction(type="shortcut", keys="shift+Print"),
        keywords=("screenshot", "captura", "recorte"),
    ),
    PredefinedCommandDefinition(
        command_id="display_screenshot_window",
        label="Capturar janela",
        description="Tira um screenshot da janela ativa.",
        category="display",
        action=ShortcutAction(type="shortcut", keys="alt+Print"),
        keywords=("screenshot", "captura", "janela"),
    ),
    PredefinedCommandDefinition(
        command_id="display_record_screen",
        label="Gravar tela",
        description="Inicia ou encerra a gravação de tela do GNOME.",
        category="display",
        action=ShortcutAction(type="shortcut", keys="ctrl+alt+shift+r"),
        keywords=("gravação", "screen recording"),
    ),
    PredefinedCommandDefinition(
        command_id="input_next_keyboard_layout",
        label="Próximo layout de teclado",
        description="Alterna para a próxima fonte de entrada.",
        category="input",
        action=ShortcutAction(type="shortcut", keys="super+space"),
        keywords=("teclado", "layout", "idioma"),
    ),
    PredefinedCommandDefinition(
        command_id="input_previous_keyboard_layout",
        label="Layout anterior de teclado",
        description="Volta para a fonte de entrada anterior.",
        category="input",
        action=ShortcutAction(type="shortcut", keys="shift+super+space"),
        keywords=("teclado", "layout", "idioma"),
    ),
    PredefinedCommandDefinition(
        command_id="navigation_overview",
        label="Visão geral",
        description="Abre a Activities Overview do GNOME.",
        category="navigation",
        action=ShortcutAction(type="shortcut", keys="super"),
        keywords=("overview", "atividades"),
    ),
    PredefinedCommandDefinition(
        command_id="navigation_app_grid",
        label="Grade de aplicativos",
        description="Abre a grade de aplicativos.",
        category="navigation",
        action=ShortcutAction(type="shortcut", keys="super+a"),
        keywords=("apps", "launcher"),
    ),
    PredefinedCommandDefinition(
        command_id="navigation_switch_applications",
        label="Alternar aplicativos",
        description="Alterna entre aplicativos abertos.",
        category="navigation",
        action=ShortcutAction(type="shortcut", keys="alt+Tab"),
        keywords=("apps", "janela"),
    ),
    PredefinedCommandDefinition(
        command_id="navigation_open_run_dialog",
        label="Janela Executar comando",
        description="Abre a caixa Executar um comando.",
        category="navigation",
        action=ShortcutAction(type="shortcut", keys="alt+F2"),
        keywords=("run", "executar"),
    ),
    PredefinedCommandDefinition(
        command_id="navigation_notification_center",
        label="Central de notificações",
        description="Abre a área de notificações do GNOME.",
        category="navigation",
        action=ShortcutAction(type="shortcut", keys="super+v"),
        keywords=("notificações", "mensagens"),
    ),
    PredefinedCommandDefinition(
        command_id="launch_terminal",
        label="Abrir terminal",
        description="Abre o terminal padrão do GNOME.",
        category="launchers",
        action=ShortcutAction(type="shortcut", keys="ctrl+alt+t"),
        keywords=("terminal", "shell"),
    ),
    PredefinedCommandDefinition(
        command_id="launch_files",
        label="Abrir Arquivos",
        description="Abre o Nautilus em nova janela.",
        category="launchers",
        action=ShellAction(type="shell", cmd="nautilus --new-window"),
        keywords=("files", "nautilus", "pastas"),
    ),
    PredefinedCommandDefinition(
        command_id="launch_browser",
        label="Abrir navegador padrão",
        description="Abre uma nova aba ou janela no navegador padrão.",
        category="launchers",
        action=ShellAction(type="shell", cmd="gio open https://www.google.com"),
        keywords=("browser", "web"),
    ),
    PredefinedCommandDefinition(
        command_id="window_close",
        label="Fechar janela",
        description="Fecha a janela ativa.",
        category="window",
        action=ShortcutAction(type="shortcut", keys="alt+F4"),
        keywords=("janela", "close"),
    ),
    PredefinedCommandDefinition(
        command_id="window_hide",
        label="Ocultar janela",
        description="Oculta a janela ativa.",
        category="window",
        action=ShortcutAction(type="shortcut", keys="super+h"),
        keywords=("janela", "hide"),
    ),
    PredefinedCommandDefinition(
        command_id="window_maximize",
        label="Maximizar janela",
        description="Maximiza a janela ativa.",
        category="window",
        action=ShortcutAction(type="shortcut", keys="super+Up"),
        keywords=("janela", "maximize"),
    ),
    PredefinedCommandDefinition(
        command_id="window_restore",
        label="Restaurar janela",
        description="Restaura ou minimiza a janela ativa.",
        category="window",
        action=ShortcutAction(type="shortcut", keys="super+Down"),
        keywords=("janela", "restore"),
    ),
    PredefinedCommandDefinition(
        command_id="window_tile_left",
        label="Lado esquerdo",
        description="Encaixa a janela ativa na metade esquerda.",
        category="window",
        action=ShortcutAction(type="shortcut", keys="super+Left"),
        keywords=("janela", "tile"),
    ),
    PredefinedCommandDefinition(
        command_id="window_tile_right",
        label="Lado direito",
        description="Encaixa a janela ativa na metade direita.",
        category="window",
        action=ShortcutAction(type="shortcut", keys="super+Right"),
        keywords=("janela", "tile"),
    ),
    PredefinedCommandDefinition(
        command_id="workspace_next",
        label="Próximo workspace",
        description="Vai para o próximo workspace.",
        category="workspace",
        action=ShortcutAction(type="shortcut", keys="ctrl+alt+Down"),
        keywords=("workspace", "área de trabalho"),
    ),
    PredefinedCommandDefinition(
        command_id="workspace_previous",
        label="Workspace anterior",
        description="Vai para o workspace anterior.",
        category="workspace",
        action=ShortcutAction(type="shortcut", keys="ctrl+alt+Up"),
        keywords=("workspace", "área de trabalho"),
    ),
    PredefinedCommandDefinition(
        command_id="workspace_move_window_next",
        label="Mover janela para próximo workspace",
        description="Move a janela ativa para o próximo workspace.",
        category="workspace",
        action=ShortcutAction(type="shortcut", keys="shift+ctrl+alt+Down"),
        keywords=("workspace", "janela"),
    ),
    PredefinedCommandDefinition(
        command_id="workspace_move_window_previous",
        label="Mover janela para workspace anterior",
        description="Move a janela ativa para o workspace anterior.",
        category="workspace",
        action=ShortcutAction(type="shortcut", keys="shift+ctrl+alt+Up"),
        keywords=("workspace", "janela"),
    ),
    PredefinedCommandDefinition(
        command_id="settings_main",
        label="Abrir Configurações",
        description="Abre a central de configurações do GNOME.",
        category="settings",
        action=ShellAction(type="shell", cmd="gnome-control-center"),
        keywords=("settings", "configurações"),
    ),
    PredefinedCommandDefinition(
        command_id="settings_sound",
        label="Configurações de som",
        description="Abre a seção de som.",
        category="settings",
        action=ShellAction(type="shell", cmd="gnome-control-center sound"),
        keywords=("settings", "som"),
    ),
    PredefinedCommandDefinition(
        command_id="settings_display",
        label="Configurações de tela",
        description="Abre a seção de monitores.",
        category="settings",
        action=ShellAction(type="shell", cmd="gnome-control-center display"),
        keywords=("settings", "monitor", "tela"),
    ),
    PredefinedCommandDefinition(
        command_id="settings_network",
        label="Configurações de rede",
        description="Abre a seção de rede.",
        category="settings",
        action=ShellAction(type="shell", cmd="gnome-control-center wifi"),
        keywords=("settings", "wifi", "rede"),
    ),
    PredefinedCommandDefinition(
        command_id="settings_bluetooth",
        label="Configurações de bluetooth",
        description="Abre a seção de bluetooth.",
        category="settings",
        action=ShellAction(type="shell", cmd="gnome-control-center bluetooth"),
        keywords=("settings", "bluetooth"),
    ),
    PredefinedCommandDefinition(
        command_id="settings_keyboard",
        label="Configurações de teclado",
        description="Abre a seção de teclado.",
        category="settings",
        action=ShellAction(type="shell", cmd="gnome-control-center keyboard"),
        keywords=("settings", "teclado"),
    ),
    PredefinedCommandDefinition(
        command_id="settings_mouse",
        label="Configurações de mouse e touchpad",
        description="Abre a seção de mouse e touchpad.",
        category="settings",
        action=ShellAction(type="shell", cmd="gnome-control-center mouse"),
        keywords=("settings", "mouse", "touchpad"),
    ),
    PredefinedCommandDefinition(
        command_id="settings_power",
        label="Configurações de energia",
        description="Abre a seção de energia.",
        category="settings",
        action=ShellAction(type="shell", cmd="gnome-control-center power"),
        keywords=("settings", "energia"),
    ),
    PredefinedCommandDefinition(
        command_id="settings_notifications",
        label="Configurações de notificações",
        description="Abre a seção de notificações.",
        category="settings",
        action=ShellAction(type="shell", cmd="gnome-control-center notifications"),
        keywords=("settings", "notificações"),
    ),
    PredefinedCommandDefinition(
        command_id="settings_region",
        label="Configurações de região e idioma",
        description="Abre a seção de região e idioma.",
        category="settings",
        action=ShellAction(type="shell", cmd="gnome-control-center region"),
        keywords=("settings", "idioma", "teclado"),
    ),
    PredefinedCommandDefinition(
        command_id="system_lock_screen",
        label="Bloquear tela",
        description="Bloqueia a sessão atual.",
        category="system",
        action=ShortcutAction(type="shortcut", keys="super+l"),
        keywords=("lock", "tela"),
    ),
    PredefinedCommandDefinition(
        command_id="system_logout",
        label="Encerrar sessão",
        description="Abre a saída da sessão atual sem prompt.",
        category="system",
        action=ShellAction(type="shell", cmd="gnome-session-quit --logout --no-prompt"),
        keywords=("logout", "sessão"),
    ),
    PredefinedCommandDefinition(
        command_id="system_reboot",
        label="Reiniciar",
        description="Reinicia a máquina via diálogo do GNOME.",
        category="system",
        action=ShellAction(type="shell", cmd="gnome-session-quit --reboot --no-prompt"),
        keywords=("reboot", "restart"),
    ),
    PredefinedCommandDefinition(
        command_id="system_power_off",
        label="Desligar",
        description="Desliga a máquina via diálogo do GNOME.",
        category="system",
        action=ShellAction(type="shell", cmd="gnome-session-quit --power-off --no-prompt"),
        keywords=("poweroff", "shutdown"),
    ),
    PredefinedCommandDefinition(
        command_id="system_suspend",
        label="Suspender",
        description="Suspende a máquina.",
        category="system",
        action=ShellAction(type="shell", cmd="systemctl suspend"),
        keywords=("sleep", "energia"),
    ),
    PredefinedCommandDefinition(
        command_id="system_emoji_picker",
        label="Seletor de emoji",
        description="Abre o seletor de emoji do GNOME.",
        category="system",
        action=ShortcutAction(type="shortcut", keys="ctrl+period"),
        keywords=("emoji", "picker"),
    ),
)

PREDEFINED_COMMANDS_BY_ID = {
    command.command_id: command for command in PREDEFINED_COMMANDS
}


def list_predefined_commands() -> tuple[PredefinedCommandDefinition, ...]:
    return PREDEFINED_COMMANDS


def get_predefined_command(command_id: str) -> PredefinedCommandDefinition:
    try:
        return PREDEFINED_COMMANDS_BY_ID[command_id]
    except KeyError as exc:
        raise ValueError(f"unknown predefined command: {command_id!r}") from exc


def resolve_predefined_command(command_id: str) -> ResolvedPredefinedAction:
    return get_predefined_command(command_id).action


__all__ = [
    "PredefinedCategory",
    "PredefinedCommandDefinition",
    "ResolvedPredefinedAction",
    "get_predefined_command",
    "list_predefined_commands",
    "resolve_predefined_command",
]