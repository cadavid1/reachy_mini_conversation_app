"""Beeper tool: find_chat — disambiguate a contact name across networks."""

from __future__ import annotations

import logging
from typing import Any, Dict

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.integrations.beeper import get_client


logger = logging.getLogger(__name__)


class BeeperFindChat(Tool):
    name = "beeper_find_chat"
    description = (
        "Resolve a contact or chat name to one or more concrete Beeper chats. "
        "Use this before send_message or read_thread when the user said something "
        "like 'Alice' or 'mom' — there may be multiple matches across networks "
        "(e.g. 'Alice (WhatsApp)' vs 'Alice (iMessage)'). Returns all matches; ask "
        "the user which one if more than one comes back."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A name, fragment of a name, or contact handle to search for.",
            },
            "limit": {
                "type": "integer",
                "description": "Max matches to return. Default 10.",
                "default": 10,
            },
        },
        "required": ["query"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        query = (kwargs.get("query") or "").strip()
        if not query:
            return {"error": "query is required"}
        limit = int(kwargs.get("limit") or 10)

        try:
            client = get_client()
        except RuntimeError as e:
            return {"error": str(e)}
        try:
            matches = await client.search_chats(query=query, limit=limit)
        except Exception as e:
            logger.exception("beeper_find_chat failed for query=%r", query)
            return {"error": f"{type(e).__name__}: {e}"}
        return {"query": query, "matches": matches, "count": len(matches)}
