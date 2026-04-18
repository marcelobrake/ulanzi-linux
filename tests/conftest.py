"""Pytest configuration shared across the suite."""

from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Force anyio to run on asyncio when we use anyio-aware tests."""
    return "asyncio"
