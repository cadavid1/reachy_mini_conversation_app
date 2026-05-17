"""Beeper Desktop WebSocket listener.

Subscribes to `ws://localhost:23373/v1/ws` and emits incoming-only text-message
events onto an `asyncio.Queue` that the Gemini Live handler drains.

Protocol (per Beeper Desktop's experimental WS docs):

  Client → Server:
    { "type": "subscriptions.set", "requestID": "r1", "chatIDs": ["*"] }

  Server → Client (representative shape):
    {
      "type": "message.upserted",
      "seq": 42,
      "ts": 1739320000000,
      "chatID": "...",
      "ids": ["m1", "m2"],
      "entries": [{ "id": "m1", ... }]
    }

`message.upserted` fires for new messages AND for edits/reactions. We dedupe by
message id (per-process LRU) so we only announce each message once, and fall
back to a REST fetch when the entry doesn't carry enough fields to decide
whether it's an inbound text we should surface.
"""

from __future__ import annotations

import json
import asyncio
import logging
import random
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from .client import BeeperClient, get_client
from .config import BeeperConfig, load_config


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IncomingMessage:
    """The subset of a Beeper message we care about for voice readback."""

    chat_id: str
    chat_title: str | None
    sender_name: str | None
    platform: str | None
    text: str | None
    timestamp: str | None
    raw: dict[str, Any]


_listener: "BeeperListener | None" = None


class _LRUSet:
    """Tiny bounded set that drops oldest insertions. Used for message-id dedupe."""

    def __init__(self, max_size: int = 1024) -> None:
        self._od: OrderedDict[str, None] = OrderedDict()
        self._max = max_size

    def add(self, key: str) -> bool:
        """Returns True if `key` was new, False if already present."""
        if key in self._od:
            self._od.move_to_end(key)
            return False
        self._od[key] = None
        if len(self._od) > self._max:
            self._od.popitem(last=False)
        return True


class BeeperListener:
    """Long-lived WebSocket subscriber with exponential-backoff reconnect."""

    def __init__(
        self,
        config: BeeperConfig | None = None,
        client: BeeperClient | None = None,
        queue_maxsize: int = 100,
    ) -> None:
        self.config = config or load_config()
        self._client: BeeperClient | None = client  # lazy: only constructed when needed
        self.queue: asyncio.Queue[IncomingMessage] = asyncio.Queue(maxsize=queue_maxsize)
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._seen_ids = _LRUSet(max_size=2048)
        # chat_id -> monotonic expiry timestamp. Events for deferred chats are
        # dropped before they reach the queue.
        self._deferred: dict[str, float] = {}

    def defer(self, chat_id: str, ttl_seconds: float) -> None:
        """Suppress notifications from `chat_id` for `ttl_seconds`."""
        if not chat_id or ttl_seconds <= 0:
            return
        loop = asyncio.get_event_loop()
        self._deferred[chat_id] = loop.time() + ttl_seconds
        logger.info("Beeper deferral set: chat=%s for %.0fs", chat_id, ttl_seconds)

    def is_deferred(self, chat_id: str) -> bool:
        expiry = self._deferred.get(chat_id)
        if expiry is None:
            return False
        if asyncio.get_event_loop().time() >= expiry:
            self._deferred.pop(chat_id, None)
            return False
        return True

    def start(self) -> None:
        """Spawn the listener task. Safe to call repeatedly."""
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run(), name="beeper-listener")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _run(self) -> None:
        if not self.config.is_configured:
            logger.warning("Beeper listener: BEEPER_ACCESS_TOKEN missing; listener disabled.")
            return

        attempt = 0
        while not self._stop_event.is_set():
            try:
                await self._connect_and_listen()
                attempt = 0
            except asyncio.CancelledError:
                raise
            except (ConnectionClosed, WebSocketException, OSError) as e:
                attempt += 1
                delay = min(60.0, 2 ** min(attempt, 6)) + random.uniform(0, 0.5)
                logger.warning(
                    "Beeper WS error (attempt %d): %s. Reconnecting in %.1fs.",
                    attempt,
                    e,
                    delay,
                )
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                    return
                except asyncio.TimeoutError:
                    pass
            except Exception:
                logger.exception("Unexpected Beeper WS error")
                await asyncio.sleep(5)

    async def _connect_and_listen(self) -> None:
        headers = {"Authorization": f"Bearer {self.config.access_token}"}
        logger.info("Connecting to Beeper WS: %s", self.config.ws_url)

        async with websockets.connect(self.config.ws_url, additional_headers=headers) as ws:
            logger.info("Beeper WS connected; subscribing to all chats.")
            await ws.send(
                json.dumps(
                    {
                        "type": "subscriptions.set",
                        "requestID": "reachy-1",
                        "chatIDs": ["*"],
                    }
                )
            )

            async for raw in ws:
                if self._stop_event.is_set():
                    return
                await self._handle_raw(raw)

    async def _handle_raw(self, raw: str | bytes) -> None:
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("Beeper WS: non-JSON frame")
            return
        if not isinstance(event, dict):
            return

        event_type = event.get("type")

        # Acknowledgement of our subscribe call.
        if event_type == "subscriptions.updated":
            chat_ids = event.get("chatIDs") or []
            logger.info("Beeper WS subscriptions.updated: %d chats", len(chat_ids))
            return

        if event_type != "message.upserted":
            return

        chat_id = event.get("chatID") or ""
        entries = event.get("entries") or []
        if not chat_id or not entries:
            return

        if self.is_deferred(chat_id):
            logger.debug("Beeper WS: chat %s is deferred; dropping %d entries", chat_id, len(entries))
            return

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            message_id = entry.get("id")
            if not message_id or not self._seen_ids.add(message_id):
                # already announced (or no id)
                continue
            await self._dispatch_entry(chat_id, message_id, entry)

    async def _dispatch_entry(
        self,
        chat_id: str,
        message_id: str,
        entry: dict[str, Any],
    ) -> None:
        """Decide whether `entry` is a new inbound text and, if so, enqueue it."""
        # Fast path: entry already carries text + sender. Otherwise REST-fetch.
        text = entry.get("text")
        sender_name = entry.get("sender_name") or entry.get("senderName")
        is_sender = entry.get("is_sender") or entry.get("isSender")
        msg_type = entry.get("type")

        needs_fetch = text is None or is_sender is None or msg_type is None
        if needs_fetch:
            client = self._ensure_client()
            if client is None:
                logger.debug("No Beeper client available; skipping enrichment for %s", message_id)
                return
            full = await client.get_message(chat_id, message_id)
            if full is None:
                logger.debug("Beeper REST returned no message for %s", message_id)
                return
            text = full.get("text") if text is None else text
            sender_name = full.get("sender_name") if sender_name is None else sender_name
            is_sender = full.get("is_sender") if is_sender is None else is_sender
            msg_type = full.get("type") if msg_type is None else msg_type
            platform = full.get("network") or full.get("account_id")
            timestamp = full.get("timestamp")
        else:
            platform = entry.get("network") or entry.get("account_id")
            timestamp = entry.get("timestamp")

        if is_sender:
            return
        if msg_type and msg_type not in ("TEXT", "NOTICE"):
            # Skip reactions, image/voice/file etc. — text only for v1.
            return
        if not text or not str(text).strip():
            return

        incoming = IncomingMessage(
            chat_id=chat_id,
            chat_title=entry.get("chat_title"),
            sender_name=sender_name,
            platform=platform,
            text=text,
            timestamp=timestamp,
            raw=entry,
        )

        try:
            self.queue.put_nowait(incoming)
        except asyncio.QueueFull:
            logger.warning("Beeper listener queue full; dropping oldest")
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self.queue.put_nowait(incoming)

    def _ensure_client(self) -> BeeperClient | None:
        if self._client is None:
            try:
                self._client = get_client()
            except RuntimeError:
                return None
        return self._client


def get_listener() -> BeeperListener:
    """Process-wide singleton."""
    global _listener
    if _listener is None:
        _listener = BeeperListener()
    return _listener
