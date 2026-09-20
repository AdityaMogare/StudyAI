"""Shared weekly gap-report query + Discord post logic."""

from __future__ import annotations

import logging
from typing import Any

from shared.agent import generate_and_store_recommendations
from shared.config import get_settings
from shared.db import fetch_topic_coverage, get_active_course_for_guild, get_conn
from shared.discord_api import build_gap_report_embed, post_channel_message

logger = logging.getLogger(__name__)


def classify_gaps(
    rows: list[dict[str, Any]],
    *,
    open_threshold: int = 2,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    untouched = [r for r in rows if int(r["question_count"]) == 0]
    unresolved = [r for r in rows if int(r["open_count"]) >= open_threshold]
    unresolved.sort(key=lambda r: int(r["open_count"]), reverse=True)
    return untouched, unresolved


def build_and_post_gap_report(
    *,
    guild_id: str | None = None,
    channel_id: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    guild = guild_id or settings.discord_guild_id
    target_channel = channel_id or settings.report_channel_id
    if not target_channel:
        return {"ok": False, "message": "REPORT_CHANNEL_ID is not configured."}
    if not settings.discord_bot_token:
        return {"ok": False, "message": "DISCORD_BOT_TOKEN is not configured."}

    with get_conn() as conn:
        course = get_active_course_for_guild(conn, guild) if guild else None
        if not course:
            return {"ok": False, "message": "No active course found for this guild."}
        rows = fetch_topic_coverage(
            conn,
            course["id"],
            threshold=settings.similarity_threshold,
        )
        untouched, unresolved = classify_gaps(rows)
        try:
            recommendation = generate_and_store_recommendations(
                conn,
                course_id=course["id"],
                course_name=course["course_name"],
                untouched=untouched,
                unresolved=unresolved,
            )
        except Exception:
            logger.exception("TA recommendation generation failed; posting coverage only")
            recommendation = None

    embed = build_gap_report_embed(
        course_name=course["course_name"],
        untouched=untouched,
        unresolved=unresolved,
        recommendation=recommendation,
    )
    post_channel_message(
        settings.discord_bot_token,
        target_channel,
        embeds=[embed],
    )
    return {
        "ok": True,
        "message": (
            f"Posted this week's study plan for **{course['course_name']}**: "
            f"{len(untouched)} not-yet-asked, {len(unresolved)} still-open areas"
            + (
                f", exam risk **{recommendation.get('exam_risk')}**."
                if recommendation
                else "."
            )
        ),
        "untouched": len(untouched),
        "unresolved": len(unresolved),
        "course_id": str(course["id"]),
        "recommendation": recommendation,
    }
