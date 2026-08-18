"""Execute actions bound to button presses.

Runs on the host. The deck only reports button index; this module turns
that index into something meaningful on the user's machine.

Shortcuts use ``xdotool`` on X11 / ``wtype`` on Wayland if available,
falling back to ``subprocess`` failure with a clear log line. No heavy
deps like pynput are required for the MVP.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import pwd
import shlex
import shutil
import subprocess
import webbrowser
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import structlog

from ulanzi_linux.application.session_agent import GraphicalSessionAgentClient
from ulanzi_linux.application.predefined_commands import (
    canonical_command_id,
    resolve_predefined_command,
)
from ulanzi_linux.domain.button_config import (
    Action,
    PredefinedCommandAction,
    ShellAction,
    ShortcutAction,
    UrlAction,
)

logger = structlog.get_logger(__name__)

COMMON_PATH_SEGMENTS = (
    "/usr/local/sbin",
    "/usr/local/bin",
    "/usr/sbin",
    "/usr/bin",
    "/sbin",
    "/bin",
    "/snap/bin",
    "/var/lib/flatpak/exports/bin",
)
USER_PATH_SUFFIXES = (
    ".local/bin",
    ".local/share/flatpak/exports/bin",
)
SCHEMELESS_URL_PREFIX = "https://"
NO_SLASH_URL_SCHEMES = frozenset(
    {
        "about",
        "data",
        "file",
        "mailto",
        "sms",
        "tel",
    }
)
LOGIN_PATH_SENTINEL = "__ULANZI_PATH__="
SHELL_CONTROL_TOKENS = frozenset(
    {
        "|",
        "||",
        "&",
        "&&",
        ";",
        "(",
        ")",
        "<",
        ">",
        ">>",
        "2>",
        "2>>",
        "2>&1",
    }
)
DESKTOP_ENTRY_SUFFIX = ".desktop"
WINDOW_FOCUS_RETRIES = 20
WINDOW_FOCUS_DELAY_S = 0.25
WINDOW_FOCUS_POST_LAUNCH_RETRIES = 40
WINDOW_FOCUS_POST_LAUNCH_DELAY_S = 0.5
SHELL_FAILURE_FOCUS_RETRIES = 8
SHELL_FAILURE_FOCUS_DELAY_S = 0.25


@dataclass(frozen=True)
class DesktopLaunchTarget:
    desktop_id: str
    desktop_file: Path
    aliases: tuple[str, ...]
    window_tokens: tuple[str, ...]


def _split_path_entries(path_value: str | None) -> list[str]:
    if not path_value:
        return []
    return [entry for entry in path_value.split(os.pathsep) if entry]


def _merge_path_entries(*groups: Iterable[str]) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for entry in group:
            if not entry:
                continue
            normalized = os.path.expanduser(entry)
            if normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
    return os.pathsep.join(merged)


class ActionRunner:
    """Dispatch an Action to the correct executor."""

    def __init__(self) -> None:
        self._env = self._build_subprocess_env()
        self._background_tasks: set[asyncio.Task[object]] = set()
        self._desktop_targets: tuple[DesktopLaunchTarget, ...] | None = None
        self._session_agent = GraphicalSessionAgentClient(self._env)

    async def run(self, action: Action) -> None:
        if await self._delegate_to_session_agent(action):
            return
        if isinstance(action, PredefinedCommandAction):
            await self._run_predefined_command(action)
        elif isinstance(action, ShellAction):
            await self._run_shell(action)
        elif isinstance(action, ShortcutAction):
            await self._run_shortcut(action)
        elif isinstance(action, UrlAction):
            await self._run_url(action)
        else:
            logger.warning("unknown_action", action=repr(action))

    async def _delegate_to_session_agent(self, action: Action) -> bool:
        if not isinstance(action, (ShellAction, ShortcutAction, UrlAction)):
            return False
        result = await self._session_agent.dispatch(action)
        if result.status == "accepted":
            logger.info(
                "action_session_agent_accepted",
                action_type=action.type,
                detail=result.detail,
            )
            return True
        if result.status == "rejected":
            logger.warning(
                "action_session_agent_rejected",
                action_type=action.type,
                detail=result.detail,
            )
            return False
        logger.debug(
            "action_session_agent_unavailable",
            action_type=action.type,
            detail=result.detail,
        )
        return False

    async def _run_predefined_command(
        self,
        action: PredefinedCommandAction,
    ) -> None:
        command = resolve_predefined_command(action.command_id)
        logger.info(
            "action_predefined_command",
            command_id=canonical_command_id(action),
            requested_command_id=action.command_id,
            resolved_action_type=command.action.type,
        )
        await self.run(command.action)

    async def _run_shell(self, action: ShellAction) -> None:
        logger.info("action_shell", cmd=action.cmd)
        desktop_target = self._desktop_launch_target(action.cmd)
        desktop_launch_allowed = (
            desktop_target is not None
            and self._command_supports_desktop_launch(action.cmd)
        )
        if desktop_target is not None:
            existing_window_id = await self._focus_existing_desktop_target(desktop_target)
            if existing_window_id is not None:
                logger.info(
                    "action_shell_focused",
                    cmd=action.cmd,
                    desktop_id=desktop_target.desktop_id,
                    window_id=existing_window_id,
                    phase="before_launch",
                )
                return
            if desktop_launch_allowed and await self._launch_desktop_target(
                action.cmd,
                desktop_target,
            ):
                return
        proc = await asyncio.create_subprocess_shell(
            action.cmd,
            env=self._env,
            cwd=self._subprocess_cwd(),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info(
            "action_shell_spawned",
            cmd=action.cmd,
            pid=proc.pid,
        )
        # Fire-and-forget: don't block the event loop on long-running cmds.
        wait_task = asyncio.create_task(
            self._monitor_shell_proc(
                proc,
                action.cmd,
                desktop_target=(
                    desktop_target if desktop_target is not None and not desktop_launch_allowed else None
                ),
            ),
            name=f"action_shell_{id(proc)}",
        )
        self._track_background_task(wait_task)

    async def _run_shortcut(self, action: ShortcutAction) -> None:
        logger.info("action_shortcut", keys=action.keys)
        if self._which("xdotool"):
            await self._exec(
                ["xdotool", "key", action.keys],
                action_type="shortcut",
                keys=action.keys,
                tool="xdotool",
            )
        elif self._which("wtype"):
            # wtype uses different syntax; best-effort approximation.
            await self._exec(
                ["wtype", "-M", action.keys],
                action_type="shortcut",
                keys=action.keys,
                tool="wtype",
            )
        else:
            logger.error(
                "no_shortcut_tool",
                hint="install xdotool (X11) or wtype (Wayland)",
                path=self._env.get("PATH"),
            )

    async def _run_url(self, action: UrlAction) -> None:
        normalized_url = self._normalize_url(action.url)
        browser_target = self._default_browser_target()
        if browser_target is not None:
            window_id = await self._focus_existing_desktop_target(browser_target)
            if window_id is not None:
                logger.info(
                    "action_url_focused",
                    url=action.url,
                    normalized_url=normalized_url,
                    desktop_id=browser_target.desktop_id,
                    window_id=window_id,
                    phase="before_open",
                )
        logger.info("action_url", url=action.url, normalized_url=normalized_url)
        browser_candidate = self._default_browser_url_candidate(
            normalized_url,
            browser_target=browser_target,
        )
        if browser_candidate is not None:
            candidate_target, argv = browser_candidate
            exit_code = await self._try_exec(argv)
            if exit_code == 0:
                logger.info(
                    "action_url_opened",
                    url=action.url,
                    normalized_url=normalized_url,
                    opener="default_browser_exec",
                    desktop_id=candidate_target.desktop_id,
                )
                window_id = await self._focus_desktop_target(candidate_target)
                if window_id is not None:
                    logger.info(
                        "action_url_focused",
                        url=action.url,
                        normalized_url=normalized_url,
                        desktop_id=candidate_target.desktop_id,
                        window_id=window_id,
                        phase="after_open",
                    )
                return
            logger.warning(
                "action_url_opener_failed",
                url=action.url,
                normalized_url=normalized_url,
                opener="default_browser_exec",
                desktop_id=candidate_target.desktop_id,
                exit_code=exit_code,
            )
        for argv in self._url_open_candidates(normalized_url):
            exit_code = await self._try_exec(argv)
            if exit_code == 0:
                logger.info(
                    "action_url_opened",
                    url=action.url,
                    normalized_url=normalized_url,
                    opener=argv[0],
                )
                if browser_target is not None:
                    window_id = await self._focus_desktop_target(browser_target)
                    if window_id is not None:
                        logger.info(
                            "action_url_focused",
                            url=action.url,
                            normalized_url=normalized_url,
                            desktop_id=browser_target.desktop_id,
                            window_id=window_id,
                            phase="after_open",
                        )
                return
            logger.warning(
                "action_url_opener_failed",
                url=action.url,
                normalized_url=normalized_url,
                opener=argv[0],
                exit_code=exit_code,
            )

        # Fall back to the stdlib registry as a last resort.
        loop = asyncio.get_running_loop()
        opened = await loop.run_in_executor(
            None,
            webbrowser.open,
            normalized_url,
        )
        if opened:
            logger.info(
                "action_url_opened",
                url=action.url,
                normalized_url=normalized_url,
                opener="webbrowser",
            )
            if browser_target is not None:
                window_id = await self._focus_desktop_target(browser_target)
                if window_id is not None:
                    logger.info(
                        "action_url_focused",
                        url=action.url,
                        normalized_url=normalized_url,
                        desktop_id=browser_target.desktop_id,
                        window_id=window_id,
                        phase="after_open",
                    )
            return
        logger.error(
            "action_url_failed",
            url=action.url,
            normalized_url=normalized_url,
            reason="no_supported_opener",
        )

    def _url_open_candidates(self, url: str) -> list[list[str]]:
        candidates: list[list[str]] = []
        for argv in (
            ["gio", "open", url],
            ["xdg-open", url],
            ["sensible-browser", url],
        ):
            if self._which(argv[0]):
                candidates.append(argv)
        return candidates

    async def _exec(self, argv: list[str], **fields: object) -> None:
        exit_code = await self._try_exec(argv)
        if exit_code == 0:
            logger.info(
                "action_exec_succeeded",
                argv=argv,
                **fields,
            )
        else:
            logger.warning(
                "action_exec_failed",
                argv=argv,
                exit_code=exit_code,
                **fields,
            )

    async def _try_exec(self, argv: list[str]) -> int:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            env=self._env,
            cwd=self._subprocess_cwd(),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        return await proc.wait()

    async def _launch_desktop_target(
        self,
        command: str,
        target: DesktopLaunchTarget,
    ) -> bool:
        for argv in self._desktop_launch_candidates(target):
            exit_code = await self._try_exec(argv)
            if exit_code == 0:
                logger.info(
                    "action_shell_opened",
                    cmd=command,
                    opener=argv[0],
                    desktop_id=target.desktop_id,
                )
                self._schedule_shell_focus_after_launch(command, target, opener=argv[0])
                return True
            logger.warning(
                "action_shell_opener_failed",
                cmd=command,
                opener=argv[0],
                desktop_id=target.desktop_id,
                exit_code=exit_code,
            )
        return False

    async def _monitor_shell_proc(
        self,
        proc: asyncio.subprocess.Process,
        cmd: str,
        *,
        desktop_target: DesktopLaunchTarget | None = None,
    ) -> int:
        exit_code = await proc.wait()
        if exit_code == 0:
            logger.info(
                "action_shell_completed",
                cmd=cmd,
                pid=proc.pid,
                exit_code=exit_code,
            )
            if desktop_target is not None:
                self._schedule_shell_focus_after_launch(cmd, desktop_target, opener="shell")
        else:
            logger.warning(
                "action_shell_failed",
                cmd=cmd,
                pid=proc.pid,
                exit_code=exit_code,
            )
            if desktop_target is not None:
                window_id = await self._focus_desktop_target_with_retries(
                    desktop_target,
                    retries=SHELL_FAILURE_FOCUS_RETRIES,
                    delay_s=SHELL_FAILURE_FOCUS_DELAY_S,
                )
                if window_id is not None:
                    logger.info(
                        "action_shell_focused",
                        cmd=cmd,
                        desktop_id=desktop_target.desktop_id,
                        window_id=window_id,
                        phase="after_failure",
                    )
                    return exit_code
                await self._launch_desktop_target(cmd, desktop_target)
        return exit_code

    def _track_background_task(self, task: asyncio.Task[object]) -> None:
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _schedule_shell_focus_after_launch(
        self,
        command: str,
        target: DesktopLaunchTarget,
        *,
        opener: str,
    ) -> None:
        task = asyncio.create_task(
            self._focus_shell_after_launch(command, target, opener=opener),
            name=(
                f"action_shell_focus_{target.desktop_id}_"
                f"{hashlib.sha256(command.encode('utf-8')).hexdigest()[:8]}"
            ),
        )
        self._track_background_task(task)

    async def _focus_shell_after_launch(
        self,
        command: str,
        target: DesktopLaunchTarget,
        *,
        opener: str,
    ) -> None:
        window_id = await self._focus_desktop_target_with_retries(
            target,
            retries=WINDOW_FOCUS_POST_LAUNCH_RETRIES,
            delay_s=WINDOW_FOCUS_POST_LAUNCH_DELAY_S,
        )
        if window_id is not None:
            logger.info(
                "action_shell_focused",
                cmd=command,
                desktop_id=target.desktop_id,
                window_id=window_id,
                phase="after_launch",
            )
            return
        logger.warning(
            "action_shell_window_not_found",
            cmd=command,
            opener=opener,
            desktop_id=target.desktop_id,
            window_tokens=target.window_tokens,
        )

    def _which(self, executable: str) -> str | None:
        return shutil.which(executable, path=self._env.get("PATH"))

    def _subprocess_cwd(self) -> str:
        return self._env.get("HOME", str(Path.home()))

    def _build_subprocess_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["PATH"] = _merge_path_entries(
            _split_path_entries(self._login_shell_path()),
            _split_path_entries(env.get("PATH")),
            self._user_specific_path_entries(),
            COMMON_PATH_SEGMENTS,
        )
        return env

    def _login_shell_path(self) -> str | None:
        shell = self._login_shell()
        if not shell:
            return None
        try:
            result = subprocess.run(
                [
                    shell,
                    "-lc",
                    f'command printf "{LOGIN_PATH_SENTINEL}%s" "$PATH"',
                ],
                capture_output=True,
                check=False,
                text=True,
                env={
                    **os.environ,
                    "SHELL": shell,
                },
            )
        except OSError as exc:
            logger.warning(
                "action_runner_login_shell_exec_failed",
                shell=shell,
                error=str(exc),
            )
            return None
        if result.returncode != 0:
            logger.warning(
                "action_runner_login_shell_path_failed",
                shell=shell,
                exit_code=result.returncode,
            )
            return None
        _, separator, tail = result.stdout.partition(LOGIN_PATH_SENTINEL)
        value = tail.strip() if separator else ""
        return value or None

    def _login_shell(self) -> str | None:
        shell = os.environ.get("SHELL", "").strip()
        if shell and Path(shell).is_file():
            return shell
        with contextlib.suppress(KeyError):
            passwd_shell = pwd.getpwuid(os.getuid()).pw_shell.strip()
            if passwd_shell and Path(passwd_shell).is_file():
                return passwd_shell
        return None

    def _user_specific_path_entries(self) -> list[str]:
        home = Path.home()
        return [str(home / suffix) for suffix in USER_PATH_SUFFIXES]

    def _desktop_launch_target(self, command: str) -> DesktopLaunchTarget | None:
        executable = self._command_executable(command)
        if not executable:
            return None
        exact_matches: list[DesktopLaunchTarget] = []
        partial_matches: list[DesktopLaunchTarget] = []
        for target in self._desktop_targets_for_session():
            if executable in target.aliases:
                exact_matches.append(target)
                continue
            if any(executable in alias for alias in target.aliases):
                partial_matches.append(target)
        if exact_matches:
            return exact_matches[0]
        if partial_matches:
            return partial_matches[0]
        return None

    def _command_supports_desktop_launch(self, command: str) -> bool:
        argv = self._simple_command_argv(command)
        return argv is not None and len(argv) == 1

    def _desktop_targets_for_session(self) -> tuple[DesktopLaunchTarget, ...]:
        if self._desktop_targets is not None:
            return self._desktop_targets

        targets: list[DesktopLaunchTarget] = []
        seen_ids: set[str] = set()
        for directory in self._desktop_entry_dirs():
            if not directory.is_dir():
                continue
            for desktop_file in sorted(directory.glob(f"*{DESKTOP_ENTRY_SUFFIX}")):
                desktop_id = desktop_file.name
                if desktop_id in seen_ids:
                    continue
                seen_ids.add(desktop_id)
                targets.append(
                    DesktopLaunchTarget(
                        desktop_id=desktop_id,
                        desktop_file=desktop_file,
                        aliases=self._desktop_aliases(desktop_file),
                        window_tokens=self._desktop_window_tokens(desktop_file),
                    )
                )

        self._desktop_targets = tuple(targets)
        return self._desktop_targets

    def _desktop_entry_dirs(self) -> list[Path]:
        candidates = [
            Path(self._env.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
            / "applications",
            Path.home() / ".local/share/applications",
            Path.home() / ".local/share/flatpak/exports/share/applications",
            Path("/var/lib/flatpak/exports/share/applications"),
            Path("/var/lib/snapd/desktop/applications"),
        ]
        for base in _split_path_entries(self._env.get("XDG_DATA_DIRS")):
            candidates.append(Path(base) / "applications")
        candidates.extend(
            [
                Path("/usr/local/share/applications"),
                Path("/usr/share/applications"),
            ]
        )

        unique: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            normalized = str(path.expanduser())
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(path)
        return unique

    def _desktop_aliases(self, desktop_file: Path) -> tuple[str, ...]:
        aliases: list[str] = [desktop_file.stem.lower(), desktop_file.name.lower()]
        aliases.extend(
            part.lower() for part in desktop_file.stem.split("_") if part.strip()
        )
        exec_name = self._desktop_exec_name(desktop_file)
        if exec_name:
            aliases.append(exec_name.lower())

        merged: list[str] = []
        seen: set[str] = set()
        for alias in aliases:
            if not alias or alias in seen:
                continue
            seen.add(alias)
            merged.append(alias)
        return tuple(merged)

    def _desktop_window_tokens(self, desktop_file: Path) -> tuple[str, ...]:
        tokens: list[str] = []
        metadata = self._desktop_entry_metadata(desktop_file)
        startup_wm_class = metadata.get("StartupWMClass")
        if startup_wm_class:
            tokens.append(startup_wm_class.lower())
        name = metadata.get("Name")
        if name:
            tokens.append(name.lower())
        exec_name = self._desktop_exec_name(desktop_file)
        if exec_name:
            tokens.append(exec_name.lower())
        tokens.append(desktop_file.stem.lower())
        tokens.extend(part.lower() for part in desktop_file.stem.split("_") if part.strip())

        merged: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            if not token or token in seen:
                continue
            seen.add(token)
            merged.append(token)
        return tuple(merged)

    def _desktop_entry_metadata(self, desktop_file: Path) -> dict[str, str]:
        metadata: dict[str, str] = {}
        try:
            for raw_line in desktop_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if key in {"Exec", "StartupWMClass", "Name"} and key not in metadata:
                    metadata[key] = value.strip()
        except OSError:
            return {}
        return metadata

    def _desktop_exec_name(self, desktop_file: Path) -> str | None:
        exec_line = self._desktop_entry_metadata(desktop_file).get("Exec")
        if exec_line is None:
            return None
        return self._exec_name_from_desktop_entry(exec_line)

    def _exec_name_from_desktop_entry(self, exec_line: str) -> str | None:
        with contextlib.suppress(ValueError):
            return self._first_executable_token(shlex.split(exec_line, posix=True))
        return None

    def _command_executable(self, command: str) -> str | None:
        argv = self._simple_command_argv(command)
        if argv is None:
            return None
        executable = self._first_executable_token(argv)
        if executable is None:
            return None
        return executable.lower()

    def _first_executable_token(self, tokens: Iterable[str]) -> str | None:
        for token in tokens:
            stripped = token.strip()
            if not stripped or stripped == "env" or stripped.startswith("%"):
                continue
            if self._looks_like_env_assignment(stripped):
                continue
            return Path(stripped).name
        return None

    def _looks_like_env_assignment(self, token: str) -> bool:
        head, separator, _tail = token.partition("=")
        return bool(separator) and not token.startswith("/") and head.replace("_", "").isalnum()

    def _argv_from_desktop_entry(
        self,
        exec_line: str,
        *,
        url: str | None = None,
    ) -> list[str] | None:
        with contextlib.suppress(ValueError):
            argv: list[str] = []
            url_consumed = False
            for token in shlex.split(exec_line, posix=True):
                stripped = token.strip()
                if not stripped:
                    continue
                if stripped in {"%u", "%U", "%f", "%F"}:
                    if url is not None:
                        argv.append(url)
                        url_consumed = True
                    continue
                if stripped.startswith("%"):
                    continue
                argv.append(stripped)
            if url is not None and not url_consumed:
                argv.append(url)
            return argv or None
        return None

    def _desktop_launch_candidates(
        self,
        target: DesktopLaunchTarget,
    ) -> list[list[str]]:
        candidates: list[list[str]] = []
        if self._which("gtk-launch"):
            candidates.append(["gtk-launch", target.desktop_id])
        if self._which("gio"):
            candidates.append(["gio", "launch", str(target.desktop_file)])
        return candidates

    def _default_browser_target(self) -> DesktopLaunchTarget | None:
        desktop_id = self._default_browser_desktop_id()
        if not desktop_id:
            return None
        normalized = desktop_id.strip().lower()
        for target in self._desktop_targets_for_session():
            if target.desktop_id.lower() == normalized:
                return target
        return None

    def _default_browser_url_candidate(
        self,
        url: str,
        *,
        browser_target: DesktopLaunchTarget | None = None,
    ) -> tuple[DesktopLaunchTarget, list[str]] | None:
        target = browser_target or self._default_browser_target()
        if target is None:
            return None
        exec_line = self._desktop_entry_metadata(target.desktop_file).get("Exec")
        if exec_line is None:
            return None
        argv = self._argv_from_desktop_entry(exec_line, url=url)
        if argv is None:
            return None
        return target, argv

    def _default_browser_desktop_id(self) -> str | None:
        for argv in (
            ["xdg-settings", "get", "default-web-browser"],
            ["xdg-mime", "query", "default", "x-scheme-handler/https"],
        ):
            if self._which(argv[0]) is None:
                continue
            try:
                result = subprocess.run(
                    argv,
                    capture_output=True,
                    check=False,
                    text=True,
                    env=self._env,
                    cwd=self._subprocess_cwd(),
                )
            except OSError:
                continue
            if result.returncode == 0:
                value = result.stdout.strip()
                if value:
                    return value
        return None

    async def _focus_desktop_target(
        self,
        target: DesktopLaunchTarget,
    ) -> str | None:
        return await self._focus_desktop_target_with_retries(
            target,
            retries=WINDOW_FOCUS_RETRIES,
        )

    async def _focus_existing_desktop_target(
        self,
        target: DesktopLaunchTarget,
    ) -> str | None:
        return await self._focus_desktop_target_with_retries(target, retries=1)

    async def _focus_desktop_target_with_retries(
        self,
        target: DesktopLaunchTarget,
        *,
        retries: int,
        delay_s: float = WINDOW_FOCUS_DELAY_S,
    ) -> str | None:
        if self._which("wmctrl") is None:
            return None
        for attempt in range(retries):
            for window_id in await asyncio.to_thread(self._window_ids_for_target, target):
                activated = await asyncio.to_thread(self._activate_window_id, window_id)
                if activated:
                    return window_id
            if attempt + 1 < retries:
                await asyncio.sleep(delay_s)
        return None

    def _window_ids_for_target(self, target: DesktopLaunchTarget) -> list[str]:
        if self._which("wmctrl") is None:
            return []
        try:
            result = subprocess.run(
                ["wmctrl", "-lx"],
                capture_output=True,
                check=False,
                text=True,
                env=self._env,
                cwd=self._subprocess_cwd(),
            )
        except OSError:
            return []
        if result.returncode != 0:
            return []
        window_ids: list[str] = []
        for raw_line in result.stdout.splitlines():
            parts = raw_line.split(None, 4)
            if len(parts) < 4:
                continue
            window_id = parts[0]
            wm_class = parts[3].lower()
            title = parts[4].lower() if len(parts) > 4 else ""
            for token in target.window_tokens:
                if token in wm_class or token in title:
                    window_ids.append(window_id)
                    break
        return window_ids

    def _activate_window_id(self, window_id: str) -> bool:
        if self._which("wmctrl") is not None:
            try:
                result = subprocess.run(
                    ["wmctrl", "-i", "-a", window_id],
                    capture_output=True,
                    check=False,
                    text=True,
                    env=self._env,
                    cwd=self._subprocess_cwd(),
                )
            except OSError:
                result = None
            if result is not None and result.returncode == 0:
                return True
        if self._which("xdotool") is not None:
            try:
                decimal_window_id = str(int(window_id, 16))
                result = subprocess.run(
                    ["xdotool", "windowactivate", decimal_window_id],
                    capture_output=True,
                    check=False,
                    text=True,
                    env=self._env,
                    cwd=self._subprocess_cwd(),
                )
            except (OSError, ValueError):
                return False
            return result.returncode == 0
        return False

    def _simple_command_argv(self, command: str) -> list[str] | None:
        if any(marker in command for marker in ("\n", "\r", "`", "$(")):
            return None
        with contextlib.suppress(ValueError):
            argv = shlex.split(command, posix=True)
            if argv and not any(token in SHELL_CONTROL_TOKENS for token in argv):
                return argv
        return None

    def _normalize_url(self, raw_url: str) -> str:
        url = raw_url.strip()
        if not url:
            return url
        if url.startswith("//"):
            return f"https:{url}"
        if "://" in url:
            return url
        scheme, separator, _remainder = url.partition(":")
        if separator and scheme.lower() in NO_SLASH_URL_SCHEMES:
            return url
        return f"{SCHEMELESS_URL_PREFIX}{url}"


__all__ = ["ActionRunner"]
