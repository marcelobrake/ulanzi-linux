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

import mimetypes
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

import structlog
import yaml
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ulanzi_linux import __version__
from ulanzi_linux.application.config_loader import load_deck_config
from ulanzi_linux.domain.button_config import (
    ButtonConfig,
    DeckConfig,
    ShellAction,
    ShortcutAction,
    SwitchPageAction,
    UrlAction,
)
from ulanzi_linux.infrastructure.hid_transport import enumerate_hid_devices
from ulanzi_linux.infrastructure.ulanzi_d200 import D200_SPEC
from ulanzi_linux.interface.web.models import (
    AssetUploadResponse,
    ConfigGetResponse,
    ConfigPutRequest,
    ConfigValidateRequest,
    DeviceSummary,
    EditorActionModel,
    EditorButtonModel,
    EditorConfigPutRequest,
    EditorConfigResponse,
    EditorPageModel,
    EditorSmallWindowModel,
    HealthResponse,
    PageSummary,
    ValidationSummary,
)

logger = structlog.get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
EDITOR_BUTTON_INDICES = frozenset(range(14))
EDITOR_DEFAULT_PAGE = "main"
HOME_DIR = Path.home()
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


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


def _compact_path(path: Path | None) -> str | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    try:
        relative = resolved.relative_to(HOME_DIR)
    except ValueError:
        return str(resolved)
    return f"~/{relative.as_posix()}" if relative.parts else "~"


def _asset_preview_url(path: str | None) -> str | None:
    if not path:
        return None
    return f"/api/asset?path={quote(path)}"


def _action_to_editor(action: object | None) -> EditorActionModel:
    if action is None:
        return EditorActionModel()
    if isinstance(action, ShellAction):
        return EditorActionModel(type="shell", cmd=action.cmd)
    if isinstance(action, ShortcutAction):
        return EditorActionModel(type="shortcut", keys=action.keys)
    if isinstance(action, UrlAction):
        return EditorActionModel(type="url", url=action.url)
    if isinstance(action, SwitchPageAction):
        return EditorActionModel(type="switch_page", page=action.page)
    raise TypeError(f"unsupported action type: {type(action)!r}")


def _button_to_editor(button: ButtonConfig) -> EditorButtonModel:
    icon_path = _compact_path(button.icon_path)
    return EditorButtonModel(
        index=button.index,
        label=button.label,
        icon_path=icon_path,
        preview_url=_asset_preview_url(icon_path),
        action=_action_to_editor(button.action),
    )


def _config_to_editor_response(
    cfg: DeckConfig,
    *,
    path: Path,
    config_exists: bool,
) -> EditorConfigResponse:
    return EditorConfigResponse(
        path=str(path),
        config_exists=config_exists,
        default_page=cfg.default_page,
        pages=[
            EditorPageModel(
                name=page.name,
                buttons=[_button_to_editor(button) for button in page.buttons],
            )
            for page in cfg.pages.values()
        ],
        fixed_buttons=[_button_to_editor(button) for button in cfg.fixed_buttons],
        small_window=EditorSmallWindowModel(
            enabled=cfg.small_window.enabled,
            interval_s=cfg.small_window.interval_s,
            time_format=cfg.small_window.time_format,
        ),
    )


def _default_editor_response(config_path: Path) -> EditorConfigResponse:
    return EditorConfigResponse(
        path=str(config_path),
        config_exists=False,
        default_page=EDITOR_DEFAULT_PAGE,
        pages=[EditorPageModel(name=EDITOR_DEFAULT_PAGE)],
        fixed_buttons=[],
        small_window=EditorSmallWindowModel(),
    )


def _validate_button_indices(
    buttons: list[EditorButtonModel],
    *,
    scope: str,
) -> None:
    seen: set[int] = set()
    for button in buttons:
        if button.index not in EDITOR_BUTTON_INDICES:
            raise ValueError(
                f"button index {button.index} is outside the visual editor layout "
                f"({min(EDITOR_BUTTON_INDICES)}..{max(EDITOR_BUTTON_INDICES)})"
            )
        if button.index in seen:
            raise ValueError(
                f"duplicate button index {button.index} in {scope}"
            )
        seen.add(button.index)


def _editor_action_to_doc(action: EditorActionModel) -> dict[str, str] | None:
    if action.type == "none":
        return None
    if action.type == "shell":
        if not action.cmd.strip():
            raise ValueError("shell action requires cmd")
        return {"type": "shell", "cmd": action.cmd}
    if action.type == "shortcut":
        if not action.keys.strip():
            raise ValueError("shortcut action requires keys")
        return {"type": "shortcut", "keys": action.keys}
    if action.type == "url":
        if not action.url.strip():
            raise ValueError("url action requires url")
        return {"type": "url", "url": action.url}
    if action.type == "switch_page":
        if not action.page.strip():
            raise ValueError("switch_page action requires page")
        return {"type": "switch_page", "page": action.page}
    raise ValueError(f"unknown editor action type: {action.type!r}")


def _editor_button_to_doc(button: EditorButtonModel) -> dict[str, Any]:
    doc: dict[str, Any] = {"index": button.index}
    if button.label:
        doc["label"] = button.label
    if button.icon_path:
        doc["icon"] = button.icon_path
    action = _editor_action_to_doc(button.action)
    if action is not None:
        doc["action"] = action
    return doc


def _editor_payload_to_yaml_text(req: EditorConfigPutRequest) -> str:
    pages_doc: dict[str, Any] = {}
    page_names: list[str] = []
    for page in req.pages:
        page_name = page.name.strip()
        if not page_name:
            raise ValueError("page name cannot be empty")
        if page_name in pages_doc:
            raise ValueError(f"duplicate page name: {page_name}")
        _validate_button_indices(page.buttons, scope=f"page {page_name!r}")
        pages_doc[page_name] = {
            "buttons": [
                _editor_button_to_doc(button)
                for button in sorted(page.buttons, key=lambda item: item.index)
            ]
        }
        page_names.append(page_name)

    if not pages_doc:
        raise ValueError("at least one page is required")

    default_page = req.default_page.strip()
    if not default_page:
        raise ValueError("default_page cannot be empty")
    if default_page not in pages_doc:
        raise ValueError(
            f"default_page {default_page!r} is not in pages {page_names!r}"
        )

    _validate_button_indices(req.fixed_buttons, scope="fixed_buttons")

    doc: dict[str, Any] = {
        "default_page": default_page,
        "small_window": {
            "enabled": req.small_window.enabled,
            "interval_s": req.small_window.interval_s,
            "time_format": req.small_window.time_format,
        },
        "pages": pages_doc,
    }
    if req.fixed_buttons:
        doc["fixed_buttons"] = [
            _editor_button_to_doc(button)
            for button in sorted(req.fixed_buttons, key=lambda item: item.index)
        ]
    return yaml.safe_dump(
        doc,
        sort_keys=False,
        allow_unicode=False,
    )


def _validate_editor_payload(
    req: EditorConfigPutRequest,
) -> tuple[ValidationSummary, str | None]:
    try:
        yaml_text = _editor_payload_to_yaml_text(req)
    except Exception as exc:  # noqa: BLE001
        return ValidationSummary(ok=False, error=str(exc)), None
    return _validate_yaml_text(yaml_text), yaml_text


def _sanitize_filename(filename: str) -> str:
    cleaned = SAFE_FILENAME_RE.sub("-", filename).strip(".-")
    return cleaned or "button-icon.png"


def _allocate_asset_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    stem = candidate.stem or "button-icon"
    suffix = candidate.suffix or ".png"
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


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

    @app.get("/api/editor", response_model=EditorConfigResponse)
    def get_editor() -> EditorConfigResponse:
        if not config_path.exists():
            return _default_editor_response(config_path)
        try:
            cfg = load_deck_config(config_path)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=422,
                detail=f"config parse failed: {exc}",
            ) from exc
        return _config_to_editor_response(
            cfg,
            path=config_path,
            config_exists=True,
        )

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

    @app.post(
        "/api/editor/validate", response_model=ValidationSummary
    )
    def validate_editor(req: EditorConfigPutRequest) -> ValidationSummary:
        summary, _ = _validate_editor_payload(req)
        return summary

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

    @app.put("/api/editor", response_model=EditorConfigResponse)
    def put_editor(req: EditorConfigPutRequest) -> EditorConfigResponse:
        summary, yaml_text = _validate_editor_payload(req)
        if not summary.ok or yaml_text is None:
            return JSONResponse(
                status_code=422,
                content=summary.model_dump(),
            )  # type: ignore[return-value]

        config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            _atomic_write(config_path, yaml_text)
        except OSError as exc:
            logger.error(
                "config_save_write_failed",
                path=str(config_path),
                error=str(exc),
            )
            raise HTTPException(
                status_code=500,
                detail=f"write failed: {exc}",
            ) from exc

        cfg = load_deck_config(config_path)
        logger.info(
            "editor_config_saved",
            path=str(config_path),
            pages=[page.name for page in summary.pages],
            fixed_buttons=len(req.fixed_buttons),
        )
        return _config_to_editor_response(
            cfg,
            path=config_path,
            config_exists=True,
        )

    @app.post("/api/assets", response_model=AssetUploadResponse)
    async def upload_asset(file: UploadFile = File(...)) -> AssetUploadResponse:
        filename = _sanitize_filename(file.filename or "button-icon.png")
        target_dir = config_path.parent / "icons"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = _allocate_asset_path(target_dir, filename)

        with target.open("wb") as fh:
            await file.seek(0)
            shutil.copyfileobj(file.file, fh)

        compact = _compact_path(target)
        assert compact is not None
        logger.info(
            "asset_uploaded",
            path=str(target),
            filename=filename,
            bytes=target.stat().st_size,
        )
        return AssetUploadResponse(
            path=compact,
            preview_url=_asset_preview_url(compact) or "",
        )

    @app.get("/api/asset")
    def get_asset(path: str) -> FileResponse:
        asset_path = Path(path).expanduser().resolve()
        if not asset_path.exists() or not asset_path.is_file():
            raise HTTPException(status_code=404, detail="asset not found")
        media_type = mimetypes.guess_type(asset_path.name)[0]
        return FileResponse(asset_path, media_type=media_type)

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
