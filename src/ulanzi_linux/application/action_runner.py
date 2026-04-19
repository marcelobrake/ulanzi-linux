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
import os
import pwd
import shutil
import subprocess
import webbrowser
from collections.abc import Iterable
from pathlib import Path

import structlog

from ulanzi_linux.domain.button_config import (
    Action,
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
        self._background_tasks: set[asyncio.Task[int]] = set()

    async def run(self, action: Action) -> None:
        if isinstance(action, ShellAction):
            await self._run_shell(action)
        elif isinstance(action, ShortcutAction):
            await self._run_shortcut(action)
        elif isinstance(action, UrlAction):
            await self._run_url(action)
        else:
            logger.warning("unknown_action", action=repr(action))

    async def _run_shell(self, action: ShellAction) -> None:
        logger.info("action_shell", cmd=action.cmd)
        proc = await asyncio.create_subprocess_shell(
            action.cmd,
            env=self._env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # Fire-and-forget: don't block the event loop on long-running cmds.
        wait_task = asyncio.create_task(
            proc.wait(),
            name=f"action_shell_{id(proc)}",
        )
        self._background_tasks.add(wait_task)
        wait_task.add_done_callback(self._background_tasks.discard)

    async def _run_shortcut(self, action: ShortcutAction) -> None:
        logger.info("action_shortcut", keys=action.keys)
        if self._which("xdotool"):
            await self._exec(["xdotool", "key", action.keys])
        elif self._which("wtype"):
            # wtype uses different syntax; best-effort approximation.
            await self._exec(["wtype", "-M", action.keys])
        else:
            logger.error("no_shortcut_tool", hint="install xdotool (X11) or wtype (Wayland)")

    async def _run_url(self, action: UrlAction) -> None:
        normalized_url = self._normalize_url(action.url)
        logger.info("action_url", url=action.url, normalized_url=normalized_url)
        for argv in self._url_open_candidates(normalized_url):
            exit_code = await self._try_exec(argv)
            if exit_code == 0:
                logger.info(
                    "action_url_opened",
                    url=action.url,
                    normalized_url=normalized_url,
                    opener=argv[0],
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
            ["xdg-open", url],
            ["gio", "open", url],
            ["sensible-browser", url],
        ):
            if self._which(argv[0]):
                candidates.append(argv)
        return candidates

    async def _exec(self, argv: list[str]) -> None:
        exit_code = await self._try_exec(argv)
        if exit_code != 0:
            logger.warning(
                "action_exec_failed",
                argv=argv,
                exit_code=exit_code,
            )

    async def _try_exec(self, argv: list[str]) -> int:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            env=self._env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return await proc.wait()

    def _which(self, executable: str) -> str | None:
        return shutil.which(executable, path=self._env.get("PATH"))

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
