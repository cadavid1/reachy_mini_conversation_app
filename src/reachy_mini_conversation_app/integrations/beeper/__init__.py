"""Beeper Desktop API integration.

Exposes a lazily-constructed singleton async client and a websocket listener
that surfaces incoming `message.upserted` events to the rest of the app.

Entry points:
    get_client()    -> AsyncBeeperDesktop (cached)
    get_listener()  -> BeeperListener (cached)
"""

from __future__ import annotations

from .client import get_client
from .listener import BeeperListener, IncomingMessage, get_listener
from .config import BeeperConfig, load_config

__all__ = [
    "BeeperConfig",
    "BeeperListener",
    "IncomingMessage",
    "get_client",
    "get_listener",
    "load_config",
]
