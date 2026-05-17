"""Beeper tool: read_thread — fetch the last N messages of a chat."""

from __future__ import annotations

import logging
from typing import Any, Dict

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.integrations.beeper import get_client


logger = logging.getLogger(__name__)


class BeeperReadThread(Tool):
    name = "beeper_read_thread"
    description = (
        "Fetch the last N messages in a Beeper chat so you can summarize or read "
        "them aloud. Call this after `beeper_find_chat` has resolved which chat "
        "the user means. Returns messages oldest-to-newest with sender names."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "The Beeper chat ID, as returned by beeper_list_chats or beeper_find_chat.",
            },
            "last_n": {
                "type": "integer",
                "description": "How many messages to fetch (newest N). Default 10.",
                "default": 10,
            },
        },
        "required": ["chat_id"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        chat_id = (kwargs.get("chat_id") or "").strip()
        if not chat_id:
            return {"error": "chat_id is required"}
        last_n = int(kwargs.get("last_n") or 10)

        try:
            client = get_client()
        except RuntimeError as e:
            return {"error": str(e)}
        try:
            messages = await client.list_messages(chat_id=chat_id, limit=last_n)
        except Exception as e:
            logger.exception("beeper_read_thread failed for chat_id=%r", chat_id)
            return {"error": f"{type(e).__name__}: {e}"}
        return {"chat_id": chat_id, "messages": messages, "count": len(messages)}
