#!/usr/bin/env python3
"""Seed CS 101 syllabus topics without Bedrock chat (offline / quota workaround).

Uses the same embed_text path as production (Titan, or local 1536-d fallback).

Usage:
  set -a && source .env && set +a
  python tools/seed_syllabus_offline.py \
      --guild-id "$DISCORD_GUILD_ID" \
      --course-name "CS 101"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from shared.bedrock import embed_text  # noqa: E402
from shared.config import get_settings  # noqa: E402
from shared.db import (  # noqa: E402
    bulk_insert_topics,
    clear_syllabus_topics,
    ensure_course,
    get_conn,
    insert_agent_action,
)

# Exam-relevant topics derived from samples/syllabus_cs101.txt
CS101_TOPICS: list[dict[str, str]] = [
    {
        "topic_name": "Programming Fundamentals",
        "description": "Variables, types, control flow, functions, and basic I/O.",
    },
    {
        "topic_name": "Arrays and Linked Lists",
        "description": "Linear structures, indexing vs pointer-based lists, time/space tradeoffs.",
    },
    {
        "topic_name": "Stacks and Queues",
        "description": "LIFO/FIFO ADTs and common use cases in algorithms and systems.",
    },
    {
        "topic_name": "Hash Tables",
        "description": "Hashing, collisions, and average-case lookup performance.",
    },
    {
        "topic_name": "Trees and Binary Search Trees",
        "description": "Tree structure, BST operations, and common traversals.",
    },
    {
        "topic_name": "Searching Algorithms",
        "description": "Linear search vs binary search and when each applies.",
    },
    {
        "topic_name": "Sorting Algorithms",
        "description": "Selection, insertion, merge, and quick sort; best/worst/average cases.",
    },
    {
        "topic_name": "Big-O Analysis",
        "description": "Asymptotic notation and analyzing time/space complexity.",
    },
    {
        "topic_name": "Recursion",
        "description": "Base cases, recursive vs iterative solutions, call stacks, tree recursion.",
    },
    {
        "topic_name": "Object-Oriented Programming",
        "description": "Classes, objects, encapsulation, inheritance, and polymorphism.",
    },
    {
        "topic_name": "Complexity and Correctness",
        "description": "Loop invariants and informal proofs of correctness.",
    },
    {
        "topic_name": "Graphs BFS and DFS",
        "description": "Adjacency list/matrix representations and BFS/DFS traversal.",
    },
    {
        "topic_name": "System Design",
        "description": "Requirements, estimation, APIs, storage, cache, and scaling tradeoffs in interviews.",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline syllabus topic seed for StudyAI")
    parser.add_argument("--guild-id", required=True, help="Discord guild / server ID")
    parser.add_argument("--course-name", default="CS 101", help="Course display name")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing topics for this course before insert",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.local_mode and not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL is required (or set LOCAL_MODE=true)", file=sys.stderr)
        return 1

    print(f"Seeding {len(CS101_TOPICS)} offline topics for '{args.course_name}'...")
    prepared: list[tuple[str, str, list[float]]] = []
    for topic in CS101_TOPICS:
        blob = f"{topic['topic_name']}\n{topic['description']}".strip()
        embedding = embed_text(blob)
        prepared.append((topic["topic_name"], topic["description"], embedding))
        print(f"  - {topic['topic_name']} ({len(embedding)}-d)")

    with get_conn() as conn:
        course = ensure_course(conn, args.guild_id, args.course_name)
        if args.replace:
            clear_syllabus_topics(conn, course["id"])
            print("Cleared existing topics for course.")
        count = bulk_insert_topics(conn, course["id"], prepared)
        insert_agent_action(
            conn,
            course_id=course["id"],
            action_type="syllabus_ingest",
            input_ref="tools/seed_syllabus_offline.py",
            output_summary=f"Offline-ingested {count} syllabus topics for {args.course_name}",
            payload={
                "topic_count": count,
                "course_name": args.course_name,
                "mode": "offline",
            },
        )

    print(f"Inserted {count} topics for course '{args.course_name}' ({course['id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
