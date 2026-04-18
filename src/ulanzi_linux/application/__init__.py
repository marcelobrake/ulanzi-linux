"""Application layer — orchestrates domain objects into use cases.

Stays free of transport details (no HID, no USB, no filesystem). Depends
only on the domain layer and whatever abstractions it needs from
infrastructure.
"""

from ulanzi_linux.application.deck_service import DeckService

__all__ = ["DeckService"]
