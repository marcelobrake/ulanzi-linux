"""Observability primitives — logging, metrics, tracing.

The concrete wiring of each concern lives in its own module; the package
re-exports the public entrypoints so callers can write
``from ulanzi_linux.observability import configure_logging``.
"""

from ulanzi_linux.observability.logging import configure_logging

__all__ = ["configure_logging"]
