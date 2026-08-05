#!/usr/bin/env python3
"""Syllabus ingestion CLI — parse syllabus → Claude topics → Titan embeddings → CockroachDB.

Usage:
  export DATABASE_URL=...
  export AWS_REGION=us-east-1
  python tools/ingest_syllabus.py \\
      --file path/to/syllabus.txt \\
      --guild-id 1234567890 \\
      --course-name "CS 101"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow running from repo root without installing a package
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from shared.bedrock import embed_text, extract_topics_from_syllabus  # noqa: E402
from shared.db import bulk_insert_topics, ensure_course, get_conn  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a syllabus into StudyAI")
    parser.add_argument("--file", required=True, help="Path to syllabus text file")
    parser.add_argument("--guild-id", required=True, help="Discord guild / server ID")
    parser.add_argument("--course-name", required=True, help="Course display name")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract topics only; do not write to the database",
    )
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL") and not args.dry_run:
        print("DATABASE_URL is required", file=sys.stderr)
        return 1

    text = Path(args.file).read_text(encoding="utf-8")
    print(f"Extracting topics from {args.file} via Bedrock Claude...")
    topics = extract_topics_from_syllabus(text)
    print(f"Found {len(topics)} topics:")
    for t in topics:
        print(f"  - {t['topic_name']}")

    if args.dry_run:
        return 0

    print("Generating embeddings and inserting into CockroachDB...")
    prepared: list[tuple[str, str, list[float]]] = []
    for topic in topics:
        blob = f"{topic['topic_name']}\n{topic.get('description', '')}".strip()
        embedding = embed_text(blob)
        prepared.append((topic["topic_name"], topic.get("description", ""), embedding))

    with get_conn() as conn:
        course = ensure_course(conn, args.guild_id, args.course_name)
        count = bulk_insert_topics(conn, course["id"], prepared)

    print(f"Inserted {count} topics for course '{args.course_name}' ({course['id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
