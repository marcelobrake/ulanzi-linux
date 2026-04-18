"""Optional localhost web UI for editing ``deck.yaml``.

The web UI is a **standalone** process that only knows how to read, validate
and write the YAML config. It does not talk to the USB device directly —
apply-to-device happens through the daemon's existing hot-reload path
(``ConfigWatcher`` picks the file change up within a second).

This module is gated behind the ``[web]`` extra so users who only want the
CLI daemon don't pull in FastAPI + uvicorn unnecessarily.
"""

from __future__ import annotations

__all__: list[str] = []
