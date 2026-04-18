"""Execute actions bound to button presses.

Runs on the host. The deck only reports button index; this module turns
that index into something meaningful on the user's machine.

Shortcuts use ``xdotool`` on X11 / ``wtype`` on Wayland if available,
falling back to ``subprocess`` failure with a clear log line. No heavy
deps like pynput are required for the MVP.
"""

from __future__ import annotations

import asyncio
import shutil
import webbrowser

import structlog

from ulanzi_linux.domain.button_config import (
    Action,
    ShellAction,
    ShortcutAction,
    UrlAction,
)

logger = structlog.get_logger(__name__)


class ActionRunner:
    """Dispatch an Action to the correct executor."""

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
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # Fire-and-forget: don't block the event loop on long-running cmds.
        asyncio.create_task(proc.wait(), name=f"action_shell_{id(proc)}")

    async def _run_shortcut(self, action: ShortcutAction) -> None:
        logger.info("action_shortcut", keys=action.keys)
        if shutil.which("xdotool"):
            await self._exec(["xdotool", "key", action.keys])
        elif shutil.which("wtype"):
            # wtype uses different syntax; best-effort approximation.
            await self._exec(["wtype", "-M", action.keys])
        else:
            logger.error("no_shortcut_tool", hint="install xdotool (X11) or wtype (Wayland)")

    async def _run_url(self, action: UrlAction) -> None:
        logger.info("action_url", url=action.url)
        # webbrowser is blocking but very fast; run in executor to be safe.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, webbrowser.open, action.url)

    async def _exec(self, argv: list[str]) -> None:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()


__all__ = ["ActionRunner"]
