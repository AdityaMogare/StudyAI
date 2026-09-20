"""Discord REST + interaction signature helpers."""

from __future__ import annotations

import json
from typing import Any

import requests
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

DISCORD_API = "https://discord.com/api/v10"

# View Channel, Send Messages, Embed Links, Add Reactions,
# Read Message History, Use Application Commands
BOT_INVITE_PERMISSIONS = 2147564672


def bot_invite_url(application_id: str, *, permissions: int = BOT_INVITE_PERMISSIONS) -> str:
    return (
        "https://discord.com/oauth2/authorize"
        f"?client_id={application_id}"
        f"&permissions={permissions}"
        "&integration_type=0"
        "&scope=bot%20applications.commands"
    )


def fetch_bot_guilds(bot_token: str) -> list[dict[str, Any]]:
    response = requests.get(
        f"{DISCORD_API}/users/@me/guilds",
        headers={"Authorization": f"Bot {bot_token}"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else []


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
            "description": "Ask a CS 101 question — get an explanation and practice follow-ups",
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
            "description": "Post this week's exam study plan to the report channel",
        },
        {
            "name": "memory",
            "description": "Course memory: explained vs still open vs never asked",
        },
        {
            "name": "quiz",
            "description": "5 exam-prep questions for a syllabus topic",
            "options": [
                {
                    "name": "topic",
                    "description": "e.g. Arrays, Recursion, Hash Tables",
                    "type": 3,
                    "required": False,
                }
            ],
        },
        {
            "name": "weak-spots",
            "description": "Topics you and the class have not covered",
        },
        {
            "name": "plan",
            "description": "This week's exam study plan from classroom memory",
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
    recommendation: dict[str, Any] | None = None,
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
    fields: list[dict[str, Any]] = [
        {
            "name": f"This week: not asked yet ({len(untouched)})",
            "value": untouched_lines[:1024],
            "inline": False,
        },
        {
            "name": f"Still confusing / open ({len(unresolved)})",
            "value": unresolved_lines[:1024],
            "inline": False,
        },
    ]
    if recommendation:
        priority = recommendation.get("priority_topics") or []
        priority_lines = (
            "\n".join(f"• {name} — `/quiz {name}`" for name in priority[:5])
            or "_No priority topics._"
        )
        risk = recommendation.get("exam_risk", "unknown")
        focus = str(recommendation.get("office_hours_focus") or "")[:400]
        fields.append(
            {
                "name": f"Study plan (exam risk: {risk})",
                "value": f"{priority_lines}\n\n{focus}"[:1024],
                "inline": False,
            }
        )
    return {
        "title": f"This week's exam plan · {course_name}",
        "description": (
            "StudyAI classroom memory — what the class has not asked, what is still open, "
            "and what to drill before the exam. Students: `/quiz`, `/weak-spots`, `/plan`."
        ),
        "color": 0x1F6FEB,
        "fields": fields,
        "footer": {"text": "StudyAI · exam prep from classroom memory"},
    }
