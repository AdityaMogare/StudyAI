"""Shared capture / resolve helpers used by Lambdas and the local Discord bot."""

from __future__ import annotations

from typing import Any

from shared.db import get_conn, insert_agent_action, resolve_question_by_message_id
from shared.tutor import (  # noqa: F401
    capture_question,
    memory_digest,
    quiz_topic,
    weak_spots,
    weekly_plan,
)


def mark_resolved(
    *,
    message_id: str,
    responder_id: str,
    answer_text: str,
    answer_message_id: str,
    summary: str,
) -> dict[str, Any]:
    with get_conn() as conn:
        question = resolve_question_by_message_id(
            conn,
            message_id,
            answer_message_id=answer_message_id,
            responder_id=responder_id,
            answer_text=answer_text,
        )
        if question:
            insert_agent_action(
                conn,
                course_id=question["course_id"],
                action_type="resolve",
                input_ref=str(question["id"]),
                output_summary=summary,
                payload={"message_id": message_id, "note": answer_text},
            )
    if not question:
        return {
            "ok": False,
            "error": "question_not_found",
            "message": (
                f"No question found for message `{message_id}`. "
                "Capture it with `/ask` first."
            ),
        }
    preview = question["question_text"][:180]
    return {
        "ok": True,
        "question_id": str(question["id"]),
        "message": f"Marked as resolved in StudyAI memory: _{preview}_",
    }
