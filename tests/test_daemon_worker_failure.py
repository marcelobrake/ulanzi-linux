"""A dead worker must take the daemon down instead of leaving it idling.

``run()`` used to wait only on the stop event, so a background task that died
went unnoticed: the process stayed alive and looked healthy while the deck was
unreachable. The exhausted-reconnect error in particular was logged as a
warning by the status loop and then dropped, which defeated the whole point of
bounding the retries — nothing ever exited, so the supervisor never restarted.
"""

from __future__ import annotations

import asyncio

import pytest

from ulanzi_linux.application.daemon import DeckDaemon
from ulanzi_linux.domain.button_config import ButtonConfig, DeckConfig, Page
from ulanzi_linux.infrastructure.hid_transport import (
    TransportReconnectExhaustedError,
)


def _cfg() -> DeckConfig:
    return DeckConfig(
        pages={
            "main": Page(name="main", buttons=(ButtonConfig(index=0, label="A"),)),
        },
        default_page="main",
    )


class _StubService:
    """Just enough surface for ``run()`` — the loops themselves are stubbed."""

    spec = None

    async def listen(self):  # pragma: no cover - replaced per test
        while True:
            await asyncio.sleep(3600)
            yield None


@pytest.mark.asyncio
async def test_worker_failure_propagates_out_of_run() -> None:
    daemon = DeckDaemon(_StubService(), _cfg())

    async def exploding_status(_stop: asyncio.Event) -> None:
        raise TransportReconnectExhaustedError("gave up after 30 attempts")

    async def idle_events(stop: asyncio.Event) -> None:
        await stop.wait()

    daemon._status_loop = exploding_status  # type: ignore[method-assign]
    daemon._event_loop = idle_events  # type: ignore[method-assign]

    with pytest.raises(TransportReconnectExhaustedError):
        await asyncio.wait_for(daemon.run(), timeout=5)


@pytest.mark.asyncio
async def test_stop_event_still_shuts_down_cleanly() -> None:
    """The normal path must not regress: a stop signal exits without raising."""
    daemon = DeckDaemon(_StubService(), _cfg())
    stop = asyncio.Event()

    async def idle(stop_event: asyncio.Event) -> None:
        await stop_event.wait()

    daemon._status_loop = idle  # type: ignore[method-assign]
    daemon._event_loop = idle  # type: ignore[method-assign]

    async def stop_soon() -> None:
        await asyncio.sleep(0.05)
        stop.set()

    stopper = asyncio.create_task(stop_soon())
    await asyncio.wait_for(daemon.run(stop_event=stop), timeout=5)
    await stopper


@pytest.mark.asyncio
async def test_worker_failure_stops_the_other_workers() -> None:
    """One worker dying must wind the others down, not orphan them."""
    daemon = DeckDaemon(_StubService(), _cfg())
    sibling_cancelled = asyncio.Event()

    async def exploding_status(_stop: asyncio.Event) -> None:
        await asyncio.sleep(0.01)
        raise TransportReconnectExhaustedError("gave up after 30 attempts")

    async def long_running_events(_stop: asyncio.Event) -> None:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            sibling_cancelled.set()
            raise

    daemon._status_loop = exploding_status  # type: ignore[method-assign]
    daemon._event_loop = long_running_events  # type: ignore[method-assign]

    with pytest.raises(TransportReconnectExhaustedError):
        await asyncio.wait_for(daemon.run(), timeout=5)

    assert sibling_cancelled.is_set()
