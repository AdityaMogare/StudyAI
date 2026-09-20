"""Classroom Memory Agent — link questions to topics and record agent actions."""

from __future__ import annotations

import logging
from typing import Any, Sequence
from uuid import UUID

from shared.bedrock import recommend_ta_interventions
from shared.config import get_settings
from shared.db import (
    fetch_nearest_topics,
    fetch_recent_question_texts,
    fetch_topic_coverage,
    insert_agent_action,
    replace_question_topic_links,
)

logger = logging.getLogger(__name__)


def link_question_to_topics(
    conn: Any,
    *,
    course_id: UUID | str,
    question_id: UUID | str,
    embedding: Sequence[float],
    question_text: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """VECTOR nearest-neighbor match + persist links + agent_actions row."""
    settings = get_settings()
    matches = fetch_nearest_topics(
        conn,
        course_id=course_id,
        embedding=embedding,
        limit=top_k,
        max_distance=settings.similarity_threshold * 2.5,
        query_text=question_text,
    )
    links = [
        {
            "topic_id": m["topic_id"],
            "distance": float(m["distance"]),
            "confidence": max(0.0, 1.0 - float(m["distance"])),
        }
        for m in matches
    ]
    replace_question_topic_links(conn, question_id=question_id, links=links)

    summary_parts = [
        f"{m['topic_name']} (d={float(m['distance']):.3f})" for m in matches
    ] or ["no confident topic match"]
    insert_agent_action(
        conn,
        course_id=course_id,
        action_type="topic_link",
        input_ref=str(question_id),
        output_summary=f"Linked question to: {', '.join(summary_parts)}",
        payload={
            "question_text": question_text[:500],
            "links": [
                {
                    "topic_id": str(m["topic_id"]),
                    "topic_name": m["topic_name"],
                    "distance": float(m["distance"]),
                }
                for m in matches
            ],
        },
    )
    logger.info("Linked question %s to %d topics", question_id, len(matches))
    return matches


def generate_and_store_recommendations(
    conn: Any,
    *,
    course_id: UUID | str,
    course_name: str,
    untouched: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bedrock reasons over coverage memory; persist recommendation as agent action."""
    recent = fetch_recent_question_texts(conn, course_id, limit=10)
    recommendation = recommend_ta_interventions(
        course_name=course_name,
        untouched=untouched,
        unresolved=unresolved,
        recent_questions=recent,
    )
    insert_agent_action(
        conn,
        course_id=course_id,
        action_type="gap_recommendation",
        input_ref=str(course_id),
        output_summary=(
            f"exam_risk={recommendation.get('exam_risk')}; "
            f"priority={', '.join(recommendation.get('priority_topics') or [])}"
        ),
        payload=recommendation,
    )
    return recommendation


def format_memory_digest(
    conn: Any,
    *,
    course_id: UUID | str,
    course_name: str,
) -> str:
    """Slash-command friendly digest of agent memory."""
    settings = get_settings()
    rows = fetch_topic_coverage(
        conn, course_id, threshold=settings.similarity_threshold
    )
    untouched = [r for r in rows if int(r["question_count"]) == 0]
    unresolved = sorted(
        [r for r in rows if int(r["open_count"]) >= 2],
        key=lambda r: int(r["open_count"]),
        reverse=True,
    )
    recommendation = generate_and_store_recommendations(
        conn,
        course_id=course_id,
        course_name=course_name,
        untouched=untouched,
        unresolved=unresolved,
    )
    priority = recommendation.get("priority_topics") or []
    lines = [
        f"**StudyAI memory · {course_name}**",
        f"Topics tracked: {len(rows)} | Untouched: {len(untouched)} | Hot open clusters: {len(unresolved)}",
        f"Exam risk: **{recommendation.get('exam_risk', 'unknown')}**",
        "",
        "**Study / TA priority:**",
    ]
    if priority:
        lines.extend(f"• {name}" for name in priority[:5])
    else:
        lines.append("• No urgent gaps detected.")
    focus = recommendation.get("office_hours_focus")
    if focus:
        lines.extend(["", f"_Office hours:_ {focus}"])
    rationale = recommendation.get("rationale")
    if rationale:
        lines.extend(["", f"_{rationale}_"])
    return "\n".join(lines)
