from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ulanzi_linux.application.session_agent import (
    GraphicalSessionAgentClient,
    GraphicalSessionAgentServer,
    SessionAgentDispatchResult,
    session_agent_socket_path,
)
from ulanzi_linux.domain.button_config import ShellAction, UrlAction


def test_session_agent_socket_path_uses_xdg_runtime_dir(tmp_path: Path) -> None:
    socket_path = session_agent_socket_path({"XDG_RUNTIME_DIR": str(tmp_path)})
    assert socket_path == tmp_path / "ulanzi-linux-session-agent.sock"


@pytest.mark.asyncio
async def test_session_agent_client_returns_unavailable_when_socket_missing(
    tmp_path: Path,
) -> None:
    client = GraphicalSessionAgentClient(
        {
            "XDG_RUNTIME_DIR": str(tmp_path),
        }
    )

    result = await client.dispatch(ShellAction(type="shell", cmd="postman"))

    assert result == SessionAgentDispatchResult(
        status="unavailable",
        detail=str(tmp_path / "ulanzi-linux-session-agent.sock"),
    )


@pytest.mark.asyncio
async def test_session_agent_server_shell_uses_nohup_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    server = GraphicalSessionAgentServer(
        env={
            "HOME": str(tmp_path),
            "PATH": "/usr/bin",
            "XDG_RUNTIME_DIR": str(tmp_path),
        }
    )
    observed: dict[str, object] = {}

    class FakeProcess:
        pid = 4242

        async def wait(self) -> int:
            return 0

    async def fake_create_subprocess_shell(
        command: str,
        *,
        env: dict[str, str],
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        observed["command"] = command
        observed["cwd"] = cwd
        observed["env"] = env
        observed["start_new_session"] = start_new_session
        return FakeProcess()

    monkeypatch.setattr(
        "ulanzi_linux.application.session_agent.asyncio.create_subprocess_shell",
        fake_create_subprocess_shell,
    )

    result = await server._run_shell("chatgpt-desktop --disable-gpu --no-sandbox")

    assert result == {"ok": True, "detail": "shell_nohup"}
    assert observed["command"] == (
        "nohup sh -lc 'chatgpt-desktop --disable-gpu --no-sandbox' >/dev/null 2>&1 &"
    )
    assert observed["cwd"] == str(tmp_path)
    assert observed["start_new_session"] is True


@pytest.mark.asyncio
async def test_session_agent_client_server_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    stop = asyncio.Event()
    server = GraphicalSessionAgentServer(
        env={
            "HOME": str(tmp_path),
            "PATH": "/usr/bin",
            "XDG_RUNTIME_DIR": str(tmp_path),
        }
    )
    received: list[dict[str, object]] = []

    async def fake_dispatch(request: dict[str, object]) -> dict[str, object]:
        received.append(request)
        return {"ok": True, "detail": "gio"}

    monkeypatch.setattr(server, "_dispatch_request", fake_dispatch)
    serve_task = asyncio.create_task(server.serve(stop_event=stop))
    await asyncio.sleep(0)

    client = GraphicalSessionAgentClient(
        {
            "XDG_RUNTIME_DIR": str(tmp_path),
        }
    )
    result = await client.dispatch(UrlAction(type="url", url="example.com"))

    stop.set()
    await serve_task

    assert result == SessionAgentDispatchResult(status="accepted", detail="gio")
    assert received == [{"type": "url", "url": "example.com"}]