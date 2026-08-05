"""Discord REST + interaction signature helpers."""

from __future__ import annotations

import json
from typing import Any

import requests
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

DISCORD_API = "https://discord.com/api/v10"


def verify_discord_signature(
    *,
    public_key: str,
    signature: str,
    timestamp: str,
    body: str,
) -> bool:
    if not public_key or not signature or not timestamp:
        return False
    try:
        key = VerifyKey(bytes.fromhex(public_key))
        key.verify(f"{timestamp}{body}".encode(), bytes.fromhex(signature))
        return True
    except (BadSignatureError, ValueError):
        return False


def post_channel_message(
    bot_token: str,
    channel_id: str,
    *,
    content: str | None = None,
    embeds: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if content:
        payload["content"] = content
    if embeds:
        payload["embeds"] = embeds
    response = requests.post(
        f"{DISCORD_API}/channels/{channel_id}/messages",
        headers={
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def register_guild_commands(
    application_id: str,
    bot_token: str,
    guild_id: str,
) -> list[dict[str, Any]]:
    commands = [
        {
            "name": "resolved",
            "description": "Mark a student question as resolved",
            "options": [
                {
                    "name": "message_id",
                    "description": "Discord message ID of the original question",
                    "type": 3,
                    "required": True,
                },
                {
                    "name": "note",
                    "description": "Optional short resolution note",
                    "type": 3,
                    "required": False,
                },
            ],
        },
        {
            "name": "ask",
            "description": "Capture a study question into StudyAI",
            "options": [
                {
                    "name": "question",
                    "description": "Your question",
                    "type": 3,
                    "required": True,
                }
            ],
        },
        {
            "name": "gap-report",
            "description": "Post the current syllabus gap report now",
        },
    ]
    response = requests.put(
        f"{DISCORD_API}/applications/{application_id}/guilds/{guild_id}/commands",
        headers={
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        },
        data=json.dumps(commands),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def build_gap_report_embed(
    *,
    course_name: str,
    untouched: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
) -> dict[str, Any]:
    untouched_lines = (
        "\n".join(f"• {row['topic_name']}" for row in untouched[:15])
        or "_None — every topic has at least one question._"
    )
    unresolved_lines = (
        "\n".join(
            f"• **{row['topic_name']}** — {row['open_count']} open / {row['question_count']} total"
            for row in unresolved[:15]
        )
        or "_None — no open-question clusters._"
    )
    return {
        "title": f"Weekly Gap Report · {course_name}",
        "description": (
            "Collective blind spots before exams — topics with no questions, "
            "and topics with many still-open questions."
        ),
        "color": 0x1F6FEB,
        "fields": [
            {
                "name": f"Untouched topics ({len(untouched)})",
                "value": untouched_lines[:1024],
                "inline": False,
            },
            {
                "name": f"Unresolved areas ({len(unresolved)})",
                "value": unresolved_lines[:1024],
                "inline": False,
            },
        ],
        "footer": {"text": "StudyAI · semantic match via CockroachDB VECTOR"},
    }
