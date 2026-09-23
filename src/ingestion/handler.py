"""Ingestion Lambda: Discord messages → Bedrock embeddings → CockroachDB memory."""

from __future__ import annotations

import json
import logging
from typing import Any

from shared.bedrock import is_likely_question
from shared.config import get_settings
from shared.features import capture_question, submit_drill_attempt

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Accept Discord MESSAGE_CREATE-style payloads from API Gateway.

    Expected JSON body (gateway relay or slash-command forwarder):
    {
      "guild_id": "...",
      "channel_id": "...",
      "message_id": "...",
      "author_id": "...",
      "author_bot": false,
      "content": "..."
    }
    """
    settings = get_settings()
    body = _parse_body(event)
    if not body:
        return _response(400, {"error": "invalid JSON body"})

    if body.get("author_bot"):
        return _response(200, {"skipped": "bot_message"})

    channel_id = str(body.get("channel_id", ""))
    if settings.questions_channel_ids and channel_id not in settings.questions_channel_ids:
        return _response(200, {"skipped": "channel_not_watched"})

    content = (body.get("content") or "").strip()
    guild_id = str(body.get("guild_id") or settings.discord_guild_id)
    message_id = str(body.get("message_id", ""))
    asker_id = str(body.get("author_id", ""))

    if content and guild_id and asker_id:
        drill = submit_drill_attempt(
            guild_id=guild_id,
            asker_id=asker_id,
            attempt_text=content,
        )
        if drill.get("handled"):
            return _response(
                200,
                {"ok": True, "drill": True, "message": drill.get("message")},
            )

    if not is_likely_question(content):
        return _response(200, {"skipped": "not_a_question"})
    if not all([guild_id, channel_id, message_id, asker_id, content]):
        return _response(400, {"error": "missing required fields"})

    try:
        result = capture_question(
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=message_id,
            asker_id=asker_id,
            question_text=content,
        )
        if not result.get("ok"):
            status = 404 if result.get("error") == "no_active_course" else 500
            return _response(
                status,
                {
                    "error": result.get("error"),
                    "hint": result.get("message"),
                },
            )
        logger.info(
            "Ingested question %s topics=%s",
            result.get("question_id"),
            result.get("linked_topics"),
        )
        return _response(
            200,
            {
                "ok": True,
                "question_id": result.get("question_id"),
                "linked_topics": result.get("linked_topics"),
            },
        )
    except Exception:
        logger.exception("Ingestion failed")
        return _response(500, {"error": "ingestion_failed"})


def _parse_body(event: dict[str, Any]) -> dict[str, Any] | None:
    if "body" in event:
        raw = event["body"]
        if event.get("isBase64Encoded"):
            import base64

            raw = base64.b64decode(raw).decode("utf-8")
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return None
    return event if isinstance(event, dict) else None


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
