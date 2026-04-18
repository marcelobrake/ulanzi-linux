"""FastAPI app that serves the deck.yaml editor.

Design decisions:

* **Standalone, not embedded in the daemon.**
  The web UI never touches the USB device. It reads, validates and writes
  the YAML file. The running daemon (if any) picks the change up via its
  hot-reload ``ConfigWatcher``. This keeps the web process runnable without
  a deck plugged in — great for laptop authoring before handing the config
  to a server.

* **Atomic write.**
  ``PUT /api/config`` writes to a temp file in the same directory, validates
  by running ``load_deck_config`` on that temp file, and only ``os.replace``s
  it onto the real path if parsing succeeded. A bad paste can never leave a
  half-written YAML on disk that the daemon would then load.

* **No auth on localhost, explicit warning off-loopback.**
  Bound to ``127.0.0.1`` by default. If the caller flips ``--host`` to
  anything else, the launcher logs a loud warning — this is an editor
  with filesystem write access, it has no business on a shared network.

* **All endpoints under ``/api`` return JSON; ``/`` returns the single
  HTML page.** The static HTML/JS/CSS live in ``static/`` and are served
  by Starlette's ``StaticFiles``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ulanzi_linux import __version__
from ulanzi_linux.application.config_loader import load_deck_config
from ulanzi_linux.domain.button_config import DeckConfig
from ulanzi_linux.infrastructure.hid_transport import enumerate_hid_devices
from ulanzi_linux.infrastructure.ulanzi_d200 import D200_SPEC
from ulanzi_linux.interface.web.models import (
    ConfigGetResponse,
    ConfigPutRequest,
    ConfigValidateRequest,
    DeviceSummary,
    HealthResponse,
    PageSummary,
    ValidationSummary,
)

logger = structlog.get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


# ---------------------------------------------------------------------- #
# Pure helpers — no FastAPI dependency, easy to unit test                #
# ---------------------------------------------------------------------- #


def _summarise(cfg: DeckConfig) -> dict[str, Any]:
    """Shape a ``DeckConfig`` for the API payload."""
    return {
        "default_page": cfg.default_page,
        "pages": [
            PageSummary(
                name=page.name,
                button_count=len(page.buttons),
                indices=sorted(b.index for b in page.buttons),
            )
            for page in cfg.pages.values()
        ],
        "fixed_button_indices": sorted(b.index for b in cfg.fixed_buttons),
        "small_window_enabled": cfg.small_window.enabled,
    }


def _validate_yaml_text(text: str) -> ValidationSummary:
    """Parse YAML text through the real loader and return a summary.

    We write to a temp file because ``load_deck_config`` expects a path —
    this keeps one code path for both ``PUT`` and ``validate``, so the UI
    can never see a divergence between "validated fine" and "saved but
    broken".
    """
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    try:
        tmp.write(text)
        tmp.flush()
        tmp.close()
        cfg = load_deck_config(tmp.name)
    except Exception as exc:  # noqa: BLE001
        return ValidationSummary(ok=False, error=str(exc))
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    summary = _summarise(cfg)
    return ValidationSummary(ok=True, **summary)


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a same-directory temp + ``os.replace``.

    Rationale:
        * ``os.replace`` is atomic on POSIX if src/dst sit on the same
          filesystem — a mid-write power loss leaves either the old file
          or the new, never a truncated one.
        * Writing in the same directory guarantees the filesystem match
          without probing mount points.
    """
    path = path.expanduser()
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())  # durability — survive kernel panic
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------- #
# App factory                                                            #
# ---------------------------------------------------------------------- #


def create_app(config_path: Path) -> FastAPI:
    """Build the FastAPI instance bound to a specific YAML path.

    The path is fixed per-process: an editor that lets the URL pick the
    file would be a path-traversal foot-gun on a tool with filesystem
    write access.
    """
    config_path = Path(config_path).expanduser().resolve()

    app = FastAPI(
        title="ulanzi-linux web editor",
        description="Localhost YAML editor for the Ulanzi D200 deck config.",
        version=__version__,
    )

    # ------------------------------------------------------------------ #
    # Meta                                                                #
    # ------------------------------------------------------------------ #

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        exists = config_path.exists()
        try:
            devices = list(
                enumerate_hid_devices(
                    vendor_id=D200_SPEC.usb_vendor_id,
                    product_id=D200_SPEC.usb_product_id,
                )
            )
        except Exception as exc:  # noqa: BLE001
            # hidapi can throw on sandboxed runners; don't let it 500 a
            # health endpoint whose main job is "is the UI alive?".
            logger.warning("hid_enumerate_failed", error=str(exc))
            devices = []
        return HealthResponse(
            version=__version__,
            config_path=str(config_path),
            config_exists=exists,
            devices_found=len(devices),
        )

    @app.get("/api/devices", response_model=list[DeviceSummary])
    def devices() -> list[DeviceSummary]:
        try:
            entries = list(
                enumerate_hid_devices(
                    vendor_id=D200_SPEC.usb_vendor_id,
                    product_id=D200_SPEC.usb_product_id,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("hid_enumerate_failed", error=str(exc))
            return []
        return [
            DeviceSummary(
                manufacturer=e.get("manufacturer_string"),
                product=e.get("product_string"),
                serial=e.get("serial_number"),
                interface_number=e.get("interface_number"),
                path=(
                    e.get("path", b"").decode("utf-8", errors="replace")
                    if isinstance(e.get("path"), (bytes, bytearray))
                    else e.get("path")
                ),
            )
            for e in entries
        ]

    # ------------------------------------------------------------------ #
    # Config CRUD                                                         #
    # ------------------------------------------------------------------ #

    @app.get("/api/config", response_model=ConfigGetResponse)
    def get_config() -> ConfigGetResponse:
        if not config_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"config not found at {config_path}",
            )
        stat = config_path.stat()
        return ConfigGetResponse(
            path=str(config_path),
            content=config_path.read_text(encoding="utf-8"),
            mtime=stat.st_mtime,
            size=stat.st_size,
        )

    @app.post(
        "/api/config/validate", response_model=ValidationSummary
    )
    def validate_config(req: ConfigValidateRequest) -> ValidationSummary:
        return _validate_yaml_text(req.content)

    @app.put("/api/config", response_model=ValidationSummary)
    def put_config(req: ConfigPutRequest) -> ValidationSummary:
        # Validate BEFORE touching disk. If the YAML is broken the daemon
        # would refuse to reload anyway (atomic swap in daemon), but the
        # user would have a broken file on disk until the next save.
        summary = _validate_yaml_text(req.content)
        if not summary.ok:
            logger.info(
                "config_save_rejected",
                path=str(config_path),
                error=summary.error,
            )
            # 422 = validation error; body carries the diagnostic.
            return JSONResponse(
                status_code=422, content=summary.model_dump()
            )  # type: ignore[return-value]

        # Ensure parent dir exists — first-time save on a fresh box.
        config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            _atomic_write(config_path, req.content)
        except OSError as exc:
            logger.error(
                "config_save_write_failed",
                path=str(config_path),
                error=str(exc),
            )
            raise HTTPException(
                status_code=500, detail=f"write failed: {exc}"
            ) from exc
        logger.info(
            "config_saved",
            path=str(config_path),
            bytes=len(req.content.encode("utf-8")),
            pages=[p.name for p in summary.pages],
        )
        return summary

    # ------------------------------------------------------------------ #
    # Static frontend                                                     #
    # ------------------------------------------------------------------ #

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR)),
        name="static",
    )

    return app


__all__ = ["create_app"]
