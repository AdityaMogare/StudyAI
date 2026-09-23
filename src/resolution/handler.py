"""Resolution Lambda: Discord interactions → CockroachDB agent memory."""

from __future__ import annotations

import json
import logging
from typing import Any

from shared.bedrock import is_likely_question
from shared.config import get_settings
from shared.discord_api import verify_discord_signature
from shared.features import (  # noqa: E402
    capture_question,
    interview_ready,
    mark_resolved,
    memory_digest,
    quiz_topic,
    start_drill,
    weak_spots,
    weekly_plan,
)
from shared.gap_logic import build_and_post_gap_report

logger = logging.getLogger()
logger.setLevel(logging.INFO)

PING = 1
APPLICATION_COMMAND = 2
MESSAGE_COMPONENT = 3


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    settings = get_settings()
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    raw_body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        import base64

        raw_body = base64.b64decode(raw_body).decode("utf-8")

    try:
        body = json.loads(raw_body or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "invalid_json"})

    # Discord Interactions Endpoint requires Ed25519 verification.
    # Gateway-forwarded reaction payloads use {"event": "reaction_add"} instead.
    is_discord_interaction = "type" in body
    if is_discord_interaction and settings.discord_public_key:
        ok = verify_discord_signature(
            public_key=settings.discord_public_key,
            signature=headers.get("x-signature-ed25519", ""),
            timestamp=headers.get("x-signature-timestamp", ""),
            body=raw_body,
        )
        if not ok:
            return _response(401, {"error": "invalid_signature"})

    if body.get("type") == PING:
        return _response(200, {"type": 1})

    interaction_type = body.get("type")
    try:
        if interaction_type == APPLICATION_COMMAND:
            return _handle_command(body)
        if interaction_type == MESSAGE_COMPONENT:
            return _handle_component(body)
        if body.get("event") == "reaction_add":
            return _handle_reaction_payload(body)
    except Exception:
        logger.exception("Resolution handler failed")
        return _discord_message(
            "StudyAI hit an error updating memory. Please try again in a moment."
        )

    return _discord_message("Unsupported interaction.")


def _handle_command(body: dict[str, Any]) -> dict[str, Any]:
    data = body.get("data") or {}
    name = data.get("name")
    options = {opt["name"]: opt.get("value") for opt in data.get("options") or []}
    user = (body.get("member") or {}).get("user") or body.get("user") or {}
    user_id = str(user.get("id", ""))
    guild_id = str(body.get("guild_id", ""))

    if name == "resolved":
        message_id = str(options.get("message_id", ""))
        note = str(options.get("note") or "Marked resolved via /resolved")
        result = mark_resolved(
            message_id=message_id,
            responder_id=user_id,
            answer_text=note,
            answer_message_id=f"slash-{message_id}-{user_id}",
            summary=f"Resolved via /resolved by {user_id}",
        )
        return _discord_message(result["message"])

    if name == "ask":
        question_text = str(options.get("question", "")).strip()
        if not is_likely_question(question_text) and len(question_text) < 8:
            return _discord_message("Please provide a clearer study question.")
        channel_id = str(body.get("channel_id", ""))
        message_id = f"ask-{body.get('id')}"
        result = capture_question(
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=message_id,
            asker_id=user_id,
            question_text=question_text,
        )
        return _discord_message(result["message"])

    if name == "gap-report":
        result = build_and_post_gap_report(guild_id=guild_id)
        return _discord_message(result["message"])

    if name == "memory":
        result = memory_digest(guild_id, asker_id=user_id)
        return _discord_message(result["message"])

    if name == "quiz":
        result = quiz_topic(
            guild_id=guild_id,
            topic_query=str(options.get("topic") or "") or None,
            asker_id=user_id,
        )
        return _discord_message(result["message"])

    if name == "weak-spots":
        result = weak_spots(guild_id=guild_id, asker_id=user_id)
        return _discord_message(result["message"])

    if name == "plan":
        result = weekly_plan(guild_id=guild_id, asker_id=user_id)
        return _discord_message(result["message"])

    if name == "drill":
        result = start_drill(
            guild_id=guild_id,
            asker_id=user_id,
            topic_query=str(options.get("topic") or "") or None,
        )
        return _discord_message(result["message"])

    if name == "interview-ready":
        result = interview_ready(guild_id=guild_id, asker_id=user_id)
        return _discord_message(result["message"])

    return _discord_message(f"Unknown command: `{name}`")


def _handle_component(body: dict[str, Any]) -> dict[str, Any]:
    custom_id = (body.get("data") or {}).get("custom_id", "")
    if custom_id.startswith("resolve:"):
        message_id = custom_id.split(":", 1)[1]
        user = (body.get("member") or {}).get("user") or body.get("user") or {}
        result = mark_resolved(
            message_id=message_id,
            responder_id=str(user.get("id", "")),
            answer_text="Resolved via button",
            answer_message_id=f"btn-{body.get('id')}",
            summary="Resolved via button",
        )
        if not result.get("ok"):
            return _discord_message("Could not find that question in memory.")
        return _discord_message("Question marked resolved ✅")
    return _discord_message("Unknown component.")


def _handle_reaction_payload(body: dict[str, Any]) -> dict[str, Any]:
    emoji = body.get("emoji") or {}
    name = emoji.get("name") if isinstance(emoji, dict) else emoji
    if name not in {"✅", "white_check_mark", "heavy_check_mark"}:
        return _response(200, {"skipped": "emoji"})
    message_id = str(body.get("message_id", ""))
    user_id = str(body.get("user_id", ""))
    result = mark_resolved(
        message_id=message_id,
        responder_id=user_id,
        answer_text="Resolved via ✅ reaction",
        answer_message_id=f"react-{message_id}-{user_id}",
        summary="Resolved via reaction",
    )
    if not result.get("ok"):
        return _response(404, {"error": "question_not_found"})
    return _response(200, {"ok": True, "question_id": result.get("question_id")})


def _discord_message(content: str) -> dict[str, Any]:
    return _response(200, {"type": 4, "data": {"content": content}})


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
