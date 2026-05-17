"""Beeper Desktop API configuration.

`BEEPER_ACCESS_TOKEN` is the env var the official `beeper-desktop-api` SDK reads
natively, so we mirror that name here.

`BEEPER_BASE_URL` defaults to localhost (Topology A); on the robot's Pi
(Topology B) it points at the Windows host's tailnet IP.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_BASE_URL = "http://localhost:23373"


@dataclass(frozen=True)
class BeeperConfig:
    access_token: str | None
    base_url: str

    @property
    def ws_url(self) -> str:
        return self.base_url.replace("http://", "ws://").replace("https://", "wss://").rstrip("/") + "/v1/ws"

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token)


def load_config() -> BeeperConfig:
    return BeeperConfig(
        access_token=os.environ.get("BEEPER_ACCESS_TOKEN"),
        base_url=os.environ.get("BEEPER_BASE_URL", DEFAULT_BASE_URL),
    )
