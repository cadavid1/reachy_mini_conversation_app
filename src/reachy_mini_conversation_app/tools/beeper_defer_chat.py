"""Beeper tool: defer_chat — suppress further notifies from a chat for a while."""

from __future__ import annotations

import logging
from typing import Any, Dict

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.integrations.beeper import get_listener


logger = logging.getLogger(__name__)


class BeeperDeferChat(Tool):
    name = "beeper_defer_chat"
    description = (
        "Suppress further [SYSTEM NOTIFY] events from a specific chat for some minutes. "
        "Call this when the user says 'later' / 'not now' / 'skip' / 'shush' in response "
        "to a notify, so a chatty sender doesn't keep nagging while the user is busy. "
        "After the TTL expires, the next message from that chat will notify normally."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "The chat_id from the most recent [SYSTEM NOTIFY].",
            },
            "minutes": {
                "type": "integer",
                "description": "How long to suppress notifications for this chat. Default 15.",
                "default": 15,
            },
        },
        "required": ["chat_id"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        chat_id = (kwargs.get("chat_id") or "").strip()
        if not chat_id:
            return {"error": "chat_id is required"}
        minutes = int(kwargs.get("minutes") or 15)
        if minutes <= 0:
            return {"error": "minutes must be positive"}

        try:
            get_listener().defer(chat_id, minutes * 60)
        except Exception as e:
            logger.exception("beeper_defer_chat failed for chat_id=%r", chat_id)
            return {"error": f"{type(e).__name__}: {e}"}
        return {"deferred": True, "chat_id": chat_id, "minutes": minutes}
