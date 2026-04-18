"""Uvicorn launcher for the web editor.

Wrapping uvicorn ourselves (instead of handing a string path to
``uvicorn.run``) lets us:
    * inject the config path into ``create_app`` without side-channel env
      vars, which would collide with future multi-instance deployments;
    * log a loud warning when binding outside loopback — it's trivially
      easy to expose a filesystem-writing tool to the LAN by mistake.
"""

from __future__ import annotations

from pathlib import Path

import structlog
import uvicorn

from ulanzi_linux.interface.web.app import create_app

logger = structlog.get_logger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765  # arbitrary, unlikely to clash with anything common


def serve(
    config_path: str | Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    log_level: str = "info",
) -> None:
    """Run the web editor until the process is signalled.

    Blocks the current thread. SIGINT / SIGTERM are handled by uvicorn's
    default graceful-shutdown path.
    """
    if host not in {"127.0.0.1", "localhost", "::1"}:
        logger.warning(
            "web_ui_non_loopback_bind",
            host=host,
            note=(
                "this editor has filesystem write access — binding off "
                "loopback exposes it to anyone who can reach the host"
            ),
        )

    app = create_app(Path(config_path))
    logger.info(
        "web_ui_starting",
        host=host,
        port=port,
        config_path=str(Path(config_path).expanduser().resolve()),
    )
    uvicorn.run(app, host=host, port=port, log_level=log_level)


__all__ = ["DEFAULT_HOST", "DEFAULT_PORT", "serve"]
