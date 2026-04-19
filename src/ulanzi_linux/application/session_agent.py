"""Graphical-session bridge for host-side button actions.

The daemon can run as a user systemd service before the desktop session has
fully exported the final graphical environment. This module provides a small
Unix-socket agent that is started from the graphical login itself and receives
shell / URL / shortcut actions from the daemon, executing them from the active
desktop session.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shlex
import shutil
import subprocess
import webbrowser
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import structlog

from ulanzi_linux.domain.button_config import Action, ShellAction, ShortcutAction, UrlAction

logger = structlog.get_logger(__name__)

SESSION_AGENT_SOCKET_ENV = "ULANZI_SESSION_AGENT_SOCKET"
SESSION_AGENT_SOCKET_NAME = "ulanzi-linux-session-agent.sock"
SESSION_AGENT_TIMEOUT_S = 2.0
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


@dataclass(frozen=True, slots=True)
class SessionAgentDispatchResult:
    status: Literal["accepted", "rejected", "unavailable"]
    detail: str | None = None


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


def _runtime_dir(env: Mapping[str, str]) -> Path | None:
    configured = env.get("XDG_RUNTIME_DIR")
    if configured:
        return Path(configured)
    fallback = Path(f"/run/user/{os.getuid()}")
    if fallback.exists():
        return fallback
    return None


def session_agent_socket_path(env: Mapping[str, str] | None = None) -> Path | None:
    resolved_env = env or os.environ
    configured = resolved_env.get(SESSION_AGENT_SOCKET_ENV)
    if configured:
        return Path(configured).expanduser()
    runtime_dir = _runtime_dir(resolved_env)
    if runtime_dir is None:
        return None
    return runtime_dir / SESSION_AGENT_SOCKET_NAME


def _serialize_action(action: Action) -> dict[str, str] | None:
    if isinstance(action, ShellAction):
        return {"type": "shell", "cmd": action.cmd}
    if isinstance(action, ShortcutAction):
        return {"type": "shortcut", "keys": action.keys}
    if isinstance(action, UrlAction):
        return {"type": "url", "url": action.url}
    return None


def _normalize_url(raw_url: str) -> str:
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


class GraphicalSessionAgentClient:
    def __init__(
        self,
        env: Mapping[str, str] | None = None,
        *,
        timeout_s: float = SESSION_AGENT_TIMEOUT_S,
    ) -> None:
        self._env = dict(env or os.environ)
        self._timeout_s = timeout_s

    async def dispatch(self, action: Action) -> SessionAgentDispatchResult:
        payload = _serialize_action(action)
        if payload is None:
            return SessionAgentDispatchResult(
                status="unavailable",
                detail="unsupported_action",
            )

        socket_path = session_agent_socket_path(self._env)
        if socket_path is None:
            return SessionAgentDispatchResult(
                status="unavailable",
                detail="socket_path_unavailable",
            )

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(socket_path)),
                timeout=self._timeout_s,
            )
        except (asyncio.TimeoutError, ConnectionRefusedError, FileNotFoundError, OSError):
            return SessionAgentDispatchResult(
                status="unavailable",
                detail=str(socket_path),
            )

        try:
            writer.write(
                json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
            )
            await writer.drain()
            response_raw = await asyncio.wait_for(
                reader.readline(),
                timeout=self._timeout_s,
            )
        except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
            return SessionAgentDispatchResult(
                status="unavailable",
                detail=str(exc),
            )
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

        if not response_raw:
            return SessionAgentDispatchResult(
                status="rejected",
                detail="empty_response",
            )

        try:
            response = json.loads(response_raw.decode("utf-8"))
        except json.JSONDecodeError:
            return SessionAgentDispatchResult(
                status="rejected",
                detail="invalid_response",
            )

        detail = response.get("detail")
        if response.get("ok") is True:
            return SessionAgentDispatchResult(status="accepted", detail=str(detail or "ok"))
        return SessionAgentDispatchResult(status="rejected", detail=str(detail or "rejected"))


class GraphicalSessionAgentServer:
    def __init__(
        self,
        *,
        socket_path: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._base_env = dict(env or os.environ)
        self._socket_path = socket_path or session_agent_socket_path(self._base_env)
        if self._socket_path is None:
            raise ValueError("unable to resolve session agent socket path")
        self._env = self._build_subprocess_env(self._base_env)
        self._server: asyncio.AbstractServer | None = None

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    async def serve(self, *, stop_event: asyncio.Event) -> None:
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self._socket_path.exists():
            self._socket_path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self._socket_path),
        )
        self._socket_path.chmod(0o600)
        logger.info(
            "session_agent_started",
            socket_path=str(self._socket_path),
        )
        try:
            await stop_event.wait()
        finally:
            assert self._server is not None
            self._server.close()
            await self._server.wait_closed()
            if self._socket_path.exists():
                self._socket_path.unlink()
            logger.info(
                "session_agent_stopped",
                socket_path=str(self._socket_path),
            )

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        response: dict[str, object]
        try:
            raw = await reader.readline()
            if not raw:
                response = {"ok": False, "detail": "empty_request"}
            else:
                try:
                    request = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    response = {"ok": False, "detail": "invalid_json"}
                else:
                    response = await self._dispatch_request(request)
            writer.write(json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n")
            await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _dispatch_request(self, request: Mapping[str, object]) -> dict[str, object]:
        action_type = str(request.get("type") or "")
        if action_type == "shell":
            return await self._run_shell(str(request.get("cmd") or ""))
        if action_type == "shortcut":
            return await self._run_shortcut(str(request.get("keys") or ""))
        if action_type == "url":
            return await self._run_url(str(request.get("url") or ""))
        return {"ok": False, "detail": f"unsupported_action:{action_type}"}

    async def _run_shell(self, command: str) -> dict[str, object]:
        if not command.strip():
            return {"ok": False, "detail": "empty_shell_command"}
        wrapper = f"nohup sh -lc {shlex.quote(command)} >/dev/null 2>&1 &"
        proc = await asyncio.create_subprocess_shell(
            wrapper,
            env=self._env,
            cwd=self._subprocess_cwd(),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        exit_code = await proc.wait()
        if exit_code == 0:
            logger.info(
                "session_agent_shell_spawned",
                cmd=command,
                pid=proc.pid,
            )
            return {"ok": True, "detail": "shell_nohup"}
        logger.warning(
            "session_agent_shell_failed",
            cmd=command,
            exit_code=exit_code,
        )
        return {"ok": False, "detail": f"shell_exit_{exit_code}"}

    async def _run_shortcut(self, keys: str) -> dict[str, object]:
        if not keys.strip():
            return {"ok": False, "detail": "empty_shortcut"}
        if self._which("xdotool"):
            exit_code = await self._try_exec(["xdotool", "key", keys])
            if exit_code == 0:
                logger.info("session_agent_shortcut_sent", keys=keys, tool="xdotool")
                return {"ok": True, "detail": "xdotool"}
            return {"ok": False, "detail": f"xdotool_exit_{exit_code}"}
        if self._which("wtype"):
            exit_code = await self._try_exec(["wtype", "-M", keys])
            if exit_code == 0:
                logger.info("session_agent_shortcut_sent", keys=keys, tool="wtype")
                return {"ok": True, "detail": "wtype"}
            return {"ok": False, "detail": f"wtype_exit_{exit_code}"}
        return {"ok": False, "detail": "no_shortcut_tool"}

    async def _run_url(self, raw_url: str) -> dict[str, object]:
        normalized_url = _normalize_url(raw_url)
        for argv in self._url_open_candidates(normalized_url):
            exit_code = await self._try_exec(argv)
            if exit_code == 0:
                logger.info(
                    "session_agent_url_opened",
                    url=raw_url,
                    normalized_url=normalized_url,
                    opener=argv[0],
                )
                return {"ok": True, "detail": argv[0]}
            logger.warning(
                "session_agent_url_opener_failed",
                url=raw_url,
                normalized_url=normalized_url,
                opener=argv[0],
                exit_code=exit_code,
            )

        loop = asyncio.get_running_loop()
        opened = await loop.run_in_executor(None, webbrowser.open, normalized_url)
        if opened:
            logger.info(
                "session_agent_url_opened",
                url=raw_url,
                normalized_url=normalized_url,
                opener="webbrowser",
            )
            return {"ok": True, "detail": "webbrowser"}
        return {"ok": False, "detail": "no_supported_url_opener"}

    def _build_subprocess_env(self, env: Mapping[str, str]) -> dict[str, str]:
        merged_env = dict(env)
        merged_env["PATH"] = _merge_path_entries(
            _split_path_entries(merged_env.get("PATH")),
            self._user_specific_path_entries(merged_env),
            COMMON_PATH_SEGMENTS,
        )
        return merged_env

    def _user_specific_path_entries(self, env: Mapping[str, str]) -> list[str]:
        home = Path(env.get("HOME", str(Path.home())))
        return [str(home / suffix) for suffix in USER_PATH_SUFFIXES]

    def _subprocess_cwd(self) -> str:
        return self._env.get("HOME", str(Path.home()))

    def _which(self, executable: str) -> str | None:
        return shutil.which(executable, path=self._env.get("PATH"))

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


__all__ = [
    "GraphicalSessionAgentClient",
    "GraphicalSessionAgentServer",
    "SESSION_AGENT_SOCKET_ENV",
    "SESSION_AGENT_SOCKET_NAME",
    "SessionAgentDispatchResult",
    "session_agent_socket_path",
]