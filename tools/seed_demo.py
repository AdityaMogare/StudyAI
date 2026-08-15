#!/usr/bin/env python3
"""Seed demo questions for a repeatable StudyAI demo (requires syllabus already ingested).

Usage:
  python tools/seed_demo.py --guild-id "$DISCORD_GUILD_ID"
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from shared.agent import link_question_to_topics  # noqa: E402
from shared.bedrock import embed_text  # noqa: E402
from shared.db import get_active_course_for_guild, get_conn, insert_question  # noqa: E402

DEMO_QUESTIONS = [
    "How does binary search guarantee O(log n) time complexity?",
    "What's the difference between a stack and a queue?",
    "Can someone explain hash table collisions?",
    "Why do we need base cases in recursion?",
    "How is BFS different from DFS on graphs?",
    "I'm stuck on merge sort — how does the merge step work?",
    "What is polymorphism in OOP with a simple example?",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed StudyAI demo questions")
    parser.add_argument("--guild-id", default=os.environ.get("DISCORD_GUILD_ID", ""))
    parser.add_argument("--channel-id", default=os.environ.get("QUESTIONS_CHANNEL_IDS", "").split(",")[0])
    args = parser.parse_args()
    if not args.guild_id:
        print("guild-id / DISCORD_GUILD_ID required", file=sys.stderr)
        return 1
    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL required", file=sys.stderr)
        return 1

    with get_conn() as conn:
        course = get_active_course_for_guild(conn, args.guild_id)
        if not course:
            print("No active course — run ingest_syllabus.py first", file=sys.stderr)
            return 1
        for text in DEMO_QUESTIONS:
            embedding = embed_text(text)
            message_id = f"seed-{uuid.uuid4()}"
            row = insert_question(
                conn,
                course_id=course["id"],
                channel_id=args.channel_id or "seed-channel",
                message_id=message_id,
                asker_id="seed-bot",
                question_text=text,
                embedding=embedding,
            )
            matches = link_question_to_topics(
                conn,
                course_id=course["id"],
                question_id=row["id"],
                embedding=embedding,
                question_text=text,
            )
            topics = ", ".join(m["topic_name"] for m in matches) or "(none)"
            print(f"✓ {text[:60]}… → {topics}")
    print("Seed complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
