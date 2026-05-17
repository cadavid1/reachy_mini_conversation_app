"""Thin async wrapper around the official Beeper Desktop API SDK.

Method names verified against beeper-desktop-api 5.0.0 (introspected
2026-05-16). All paginated calls in the SDK return AsyncPaginator, so we
iterate and stop at `limit` rather than calling `.items`.
"""

from __future__ import annotations

import logging
from typing import Any

from .config import BeeperConfig, load_config


logger = logging.getLogger(__name__)


_client: "BeeperClient | None" = None


class BeeperClient:
    """Async wrapper around AsyncBeeperDesktop."""

    def __init__(self, config: BeeperConfig | None = None) -> None:
        self.config = config or load_config()
        if not self.config.is_configured:
            raise RuntimeError(
                "BEEPER_ACCESS_TOKEN is not set. Create a Bearer token in Beeper Desktop "
                "(Settings -> Developer) and put it in your .env."
            )

        # Imported lazily so the rest of the app doesn't crash on import when
        # the SDK isn't installed yet (Phase 1 vs Phase 2).
        from beeper_desktop_api import AsyncBeeperDesktop  # type: ignore[import-not-found]

        self._sdk = AsyncBeeperDesktop(
            access_token=self.config.access_token,
            base_url=self.config.base_url,
        )

    async def info(self) -> Any:
        """GET /v1/info — health check."""
        return await self._sdk.info.retrieve()

    async def list_recent_chats(self, limit: int = 20, unread_only: bool = False) -> list[dict[str, Any]]:
        """Return recent chats, most-recently-active first."""
        out: list[dict[str, Any]] = []
        async for chat in self._sdk.chats.search(limit=limit, unread_only=unread_only):
            out.append(self._chat_to_dict(chat))
            if len(out) >= limit:
                break
        return out

    async def search_chats(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Fuzzy-search chats by name / participant."""
        out: list[dict[str, Any]] = []
        async for chat in self._sdk.chats.search(query=query, limit=limit):
            out.append(self._chat_to_dict(chat))
            if len(out) >= limit:
                break
        return out

    async def get_message(self, chat_id: str, message_id: str) -> dict[str, Any] | None:
        """Retrieve a single message by id. Returns None if not found."""
        try:
            msg = await self._sdk.messages.retrieve(message_id, chat_id=chat_id)
        except Exception as e:
            logger.debug("get_message(%s) failed: %s", message_id, e)
            return None
        return self._message_to_dict(msg)

    async def list_messages(self, chat_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return up to `limit` messages from a chat, oldest-to-newest."""
        out: list[dict[str, Any]] = []
        # messages.list has no `limit` kwarg; cap by breaking out of the paginator.
        async for msg in self._sdk.messages.list(chat_id=chat_id, direction="before"):
            out.append(self._message_to_dict(msg))
            if len(out) >= limit:
                break
        out.reverse()
        return out

    async def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        """POST a plain-text message into a chat. Returns confirmation + pending id."""
        response = await self._sdk.messages.send(chat_id=chat_id, text=text)
        return {
            "sent": True,
            "chat_id": getattr(response, "chat_id", chat_id),
            "pending_message_id": getattr(response, "pending_message_id", None),
        }

    @staticmethod
    def _chat_to_dict(chat: Any) -> dict[str, Any]:
        participants_wrapper = getattr(chat, "participants", None)
        participant_items = getattr(participants_wrapper, "items", []) if participants_wrapper is not None else []
        last_activity = getattr(chat, "last_activity", None)
        return {
            "id": getattr(chat, "id", None),
            "title": getattr(chat, "title", None),
            "network": getattr(chat, "network", None),
            "account_id": getattr(chat, "account_id", None),
            "type": getattr(chat, "type", None),
            "participants": [
                getattr(p, "full_name", None) or getattr(p, "username", None) or getattr(p, "id", None)
                for p in participant_items
            ],
            "unread_count": getattr(chat, "unread_count", 0),
            "is_muted": getattr(chat, "is_muted", False),
            "last_activity": last_activity.isoformat() if last_activity is not None else None,
        }

    @staticmethod
    def _message_to_dict(msg: Any) -> dict[str, Any]:
        timestamp = getattr(msg, "timestamp", None)
        return {
            "id": getattr(msg, "id", None),
            "chat_id": getattr(msg, "chat_id", None),
            "text": getattr(msg, "text", None),
            "sender_name": getattr(msg, "sender_name", None),
            "sender_id": getattr(msg, "sender_id", None),
            "timestamp": timestamp.isoformat() if timestamp is not None else None,
            "is_sender": getattr(msg, "is_sender", False),
            "type": getattr(msg, "type", None),
            "is_unread": getattr(msg, "is_unread", None),
        }


def get_client() -> BeeperClient:
    """Lazily construct a process-wide singleton."""
    global _client
    if _client is None:
        _client = BeeperClient()
    return _client
