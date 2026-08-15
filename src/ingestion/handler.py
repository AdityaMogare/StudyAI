"""Ingestion Lambda: Discord messages → Bedrock embeddings → CockroachDB memory."""

from __future__ import annotations

import json
import logging
from typing import Any

from shared.agent import link_question_to_topics
from shared.bedrock import embed_text, is_likely_question
from shared.config import get_settings
from shared.db import get_active_course_for_guild, get_conn, insert_question

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
    if not is_likely_question(content):
        return _response(200, {"skipped": "not_a_question"})

    guild_id = str(body.get("guild_id") or settings.discord_guild_id)
    message_id = str(body.get("message_id", ""))
    asker_id = str(body.get("author_id", ""))
    if not all([guild_id, channel_id, message_id, asker_id, content]):
        return _response(400, {"error": "missing required fields"})

    try:
        embedding = embed_text(content)
        with get_conn() as conn:
            course = get_active_course_for_guild(conn, guild_id)
            if not course:
                return _response(
                    404,
                    {
                        "error": "no_active_course",
                        "hint": "Run tools/ingest_syllabus.py to create a course",
                    },
                )
            row = insert_question(
                conn,
                course_id=course["id"],
                channel_id=channel_id,
                message_id=message_id,
                asker_id=asker_id,
                question_text=content,
                embedding=embedding,
            )
            matches = link_question_to_topics(
                conn,
                course_id=course["id"],
                question_id=row["id"],
                embedding=embedding,
                question_text=content,
            )
        topic_names = [m["topic_name"] for m in matches]
        logger.info(
            "Ingested question %s for course %s topics=%s",
            row["id"],
            course["id"],
            topic_names,
        )
        return _response(
            200,
            {
                "ok": True,
                "question_id": str(row["id"]),
                "linked_topics": topic_names,
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
