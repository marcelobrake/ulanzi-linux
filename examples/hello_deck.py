"""Minimal example: open the deck, flash brightness, print button events.

Run with:
    python examples/hello_deck.py

Requires the device to be connected and the udev rule from
``udev/99-ulanzi-d200.rules`` to be installed (so you can open the device
without sudo).
"""

from __future__ import annotations

import asyncio
import contextlib

from ulanzi_linux.application.deck_service import DeckService
from ulanzi_linux.domain.events import ButtonEvent
from ulanzi_linux.observability import configure_logging


async def main() -> None:
    configure_logging(level="INFO")

    async with DeckService.open_default() as service:
        print(f"connected to {service.spec.name}")
        print(f"grid: {service.spec.button_rows}x{service.spec.button_cols} "
              f"({service.spec.button_count} buttons)")

        # Flash the LCD as a connection indicator.
        await service.set_brightness(20)
        await asyncio.sleep(0.3)
        await service.set_brightness(80)

        # Stream events until Ctrl-C.
        print("waiting for button events (Ctrl-C to stop)...")
        async for event in service.listen():
            if isinstance(event, ButtonEvent):
                verb = "pressed" if event.pressed else "released"
                print(f"  button {event.index} {verb}")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
