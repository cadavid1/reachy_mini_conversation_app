"""Beeper tool: list_unread_chats — what's recent / unread across all networks."""

from __future__ import annotations

import logging
from typing import Any, Dict

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.integrations.beeper import get_client


logger = logging.getLogger(__name__)


class BeeperListChats(Tool):
    name = "beeper_list_chats"
    description = (
        "List the user's most recently-active Beeper chats across all networks "
        "(WhatsApp, iMessage, Signal, Telegram, etc.). Use this when the user asks "
        "'who messaged me', 'what's new', or before sending a reply so you can resolve "
        "the right chat. Returns chat id, title, platform, unread count, and a preview."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "How many chats to return. Default 10.",
                "default": 10,
            }
        },
        "required": [],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        limit = int(kwargs.get("limit") or 10)
        try:
            client = get_client()
        except RuntimeError as e:
            return {"error": str(e)}
        try:
            chats = await client.list_recent_chats(limit=limit)
        except Exception as e:
            logger.exception("beeper_list_chats failed")
            return {"error": f"{type(e).__name__}: {e}"}
        return {"chats": chats, "count": len(chats)}
