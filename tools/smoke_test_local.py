#!/usr/bin/env python3
"""Local smoke test: ask → link topics, memory digest, resolve path (no Discord HTTP)."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from shared.agent import format_memory_digest, link_question_to_topics  # noqa: E402
from shared.bedrock import embed_text, recommend_ta_interventions  # noqa: E402
from shared.config import get_settings  # noqa: E402
from shared.db import (  # noqa: E402
    fetch_topic_coverage,
    get_active_course_for_guild,
    get_conn,
    insert_question,
    resolve_question_by_message_id,
)
from shared.gap_logic import classify_gaps  # noqa: E402
from shared.tutor import capture_question, quiz_topic, weak_spots, weekly_plan  # noqa: E402


def main() -> int:
    guild_id = os.environ.get("DISCORD_GUILD_ID", "")
    channel_id = (os.environ.get("QUESTIONS_CHANNEL_IDS") or "smoke-channel").split(",")[0]
    if not guild_id:
        print("DISCORD_GUILD_ID required", file=sys.stderr)
        return 1
    settings = get_settings()
    if not settings.local_mode and not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL required (or set LOCAL_MODE=true)", file=sys.stderr)
        return 1

    question_text = "How does binary search guarantee O(log n) time complexity?"
    message_id = f"smoke-{uuid.uuid4()}"

    with get_conn() as conn:
        course = get_active_course_for_guild(conn, guild_id)
        if not course:
            print("No active course — run seed_syllabus_offline.py first", file=sys.stderr)
            return 1

        print(f"Course: {course['course_name']} ({course['id']})")
        embedding = embed_text(question_text)
        row = insert_question(
            conn,
            course_id=course["id"],
            channel_id=channel_id,
            message_id=message_id,
            asker_id="smoke-tester",
            question_text=question_text,
            embedding=embedding,
        )
        matches = link_question_to_topics(
            conn,
            course_id=course["id"],
            question_id=row["id"],
            embedding=embedding,
            question_text=question_text,
        )
        topics = ", ".join(m["topic_name"] for m in matches) or "(none)"
        print(f"/ask link: {topics}")

        digest = format_memory_digest(
            conn, course_id=course["id"], course_name=course["course_name"]
        )
        print("--- /memory ---")
        print(digest[:800])

        rows = fetch_topic_coverage(conn, course["id"])
        untouched, unresolved = classify_gaps(rows)
        rec = recommend_ta_interventions(
            course_name=course["course_name"],
            untouched=untouched,
            unresolved=unresolved,
            recent_questions=[question_text],
        )
        print("--- gap recommendation ---")
        print(rec)

        resolved = resolve_question_by_message_id(
            conn,
            message_id,
            answer_message_id=f"smoke-answer-{message_id}",
            responder_id="smoke-ta",
            answer_text="Binary search halves the search space each step.",
        )
        print(f"/resolved: status={resolved and resolved.get('status')}")

    taught = capture_question(
        guild_id=guild_id,
        channel_id=channel_id,
        message_id=f"tutor-smoke-{uuid.uuid4()}",
        asker_id="smoke-tester",
        question_text="What's the difference between a stack and a queue?",
    )
    print("--- /ask tutor ---")
    print((taught.get("message") or "")[:500])
    print("--- /quiz Hash ---")
    print(quiz_topic(guild_id=guild_id, topic_query="Hash", asker_id="smoke-tester")["message"][:400])
    print("--- /weak-spots ---")
    print(weak_spots(guild_id=guild_id, asker_id="smoke-tester")["message"][:400])
    print("--- /plan ---")
    print(weekly_plan(guild_id=guild_id, asker_id="smoke-tester")["message"][:400])

    print("Smoke test OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
