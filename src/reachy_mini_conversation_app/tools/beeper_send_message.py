"""Beeper tool: send_message — write a text reply on the user's behalf.

The persona prompt MUST require explicit verbal confirmation ("yes / send /
confirm") before this tool is invoked. Once invoked, the message goes out
immediately — there is no preview state.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.integrations.beeper import get_client


logger = logging.getLogger(__name__)


class BeeperSendMessage(Tool):
    name = "beeper_send_message"
    description = (
        "Send a plain text Beeper message to a specific chat. ONLY call this after "
        "(a) you've resolved the chat via beeper_find_chat or beeper_list_chats, "
        "AND (b) the user has explicitly confirmed the recipient and exact text "
        "out loud (e.g. they said 'yes', 'send it', or 'confirm'). Do not invoke "
        "speculatively. Returns {sent: bool, message_id: str|null}."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "The Beeper chat ID returned by find_chat / list_chats.",
            },
            "text": {
                "type": "string",
                "description": "The exact message text to send. Use the user's words verbatim.",
            },
        },
        "required": ["chat_id", "text"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        chat_id = (kwargs.get("chat_id") or "").strip()
        text = kwargs.get("text") or ""
        if not chat_id:
            return {"error": "chat_id is required"}
        if not text.strip():
            return {"error": "text is required and must be non-empty"}

        try:
            client = get_client()
        except RuntimeError as e:
            return {"error": str(e)}
        try:
            result = await client.send_message(chat_id=chat_id, text=text)
            logger.info("Sent Beeper message: chat_id=%s len=%d", chat_id, len(text))
            return result
        except Exception as e:
            logger.exception("beeper_send_message failed for chat_id=%r", chat_id)
            return {"error": f"{type(e).__name__}: {e}"}
