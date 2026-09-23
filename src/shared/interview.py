"""Personal interview-prep drills. Memory is what this user fails, not class Q&A."""

from __future__ import annotations

import logging
from typing import Any

from shared.bedrock import invoke_chat, parse_json_object
from shared.cs101_tutor import curriculum_for, match_topic_name
from shared.db import (
    clear_drill_pending,
    fetch_drill_stats,
    fetch_recent_drill_questions,
    fetch_syllabus_topics,
    get_active_course_for_guild,
    get_conn,
    get_drill_pending,
    insert_agent_action,
    insert_drill_attempt,
    upsert_drill_pending,
)
from shared.local_store import tokenize
from shared.tutor import clip

logger = logging.getLogger(__name__)


def start_drill(*, guild_id: str, asker_id: str, topic_query: str | None = None) -> dict[str, Any]:
    with get_conn() as conn:
        course = get_active_course_for_guild(conn, guild_id)
        if not course:
            return {"ok": False, "message": "No active course for this server. Seed a syllabus first."}
        pending = get_drill_pending(conn, course_id=course["id"], asker_id=asker_id)
        if pending:
            return {
                "ok": True,
                "pending": True,
                "message": clip(
                    "You already have an open drill. Reply in this channel with your attempt.\n\n"
                    f"**{pending['topic_name']}**\n{pending['question_text']}"
                ),
            }
        topics = fetch_syllabus_topics(conn, course["id"])
        if not topics:
            return {"ok": False, "message": "No interview topics seeded yet."}
        stats = {str(r["topic_id"]): r for r in fetch_drill_stats(conn, course_id=course["id"], asker_id=asker_id)}
        names = [t["topic_name"] for t in topics]
        chosen_name = match_topic_name(topic_query or "", names) if topic_query else None
        topic_row = next((t for t in topics if t["topic_name"] == chosen_name), None)
        if topic_row is None:
            topic_row = _pick_weak_topic(topics, stats)
        recent = fetch_recent_drill_questions(
            conn,
            course_id=course["id"],
            asker_id=asker_id,
            topic_id=topic_row["id"],
        )
        question, hint = _pick_question(topic_row["topic_name"], recent)
        upsert_drill_pending(
            conn,
            course_id=course["id"],
            asker_id=asker_id,
            topic_id=topic_row["id"],
            topic_name=topic_row["topic_name"],
            question_text=question,
            hint=hint,
        )
        insert_agent_action(
            conn,
            course_id=course["id"],
            action_type="drill_start",
            input_ref=asker_id,
            output_summary=f"Drill started on {topic_row['topic_name']}",
            payload={"asker_id": asker_id, "topic_name": topic_row["topic_name"]},
        )
    return {
        "ok": True,
        "pending": True,
        "topic_name": topic_row["topic_name"],
        "message": clip(
            f"**Drill · {topic_row['topic_name']}**\n"
            "Answer in the next message in this channel (a few sentences is enough).\n\n"
            f"{question}\n\n"
            "_This counts toward `/interview-ready`, not class `/ask` memory._"
        ),
    }


def submit_drill_attempt(*, guild_id: str, asker_id: str, attempt_text: str) -> dict[str, Any]:
    text = (attempt_text or "").strip()
    if not text:
        return {"ok": False, "handled": False, "message": "Empty attempt."}
    with get_conn() as conn:
        course = get_active_course_for_guild(conn, guild_id)
        if not course:
            return {"ok": False, "handled": False, "message": "No active course."}
        pending = get_drill_pending(conn, course_id=course["id"], asker_id=asker_id)
        if not pending:
            return {"ok": False, "handled": False, "message": "No open drill."}
        passed, feedback = _score_attempt(
            question=pending["question_text"],
            hint=str(pending.get("hint") or ""),
            attempt=text,
            topic_name=pending["topic_name"],
        )
        insert_drill_attempt(
            conn,
            course_id=course["id"],
            asker_id=asker_id,
            topic_id=pending["topic_id"],
            topic_name=pending["topic_name"],
            question_text=pending["question_text"],
            attempt_text=text,
            passed=passed,
            feedback=feedback,
        )
        clear_drill_pending(conn, course_id=course["id"], asker_id=asker_id)
        insert_agent_action(
            conn,
            course_id=course["id"],
            action_type="drill_result",
            input_ref=asker_id,
            output_summary=(
                f"{'pass' if passed else 'fail'} · {pending['topic_name']}"
            ),
            payload={
                "asker_id": asker_id,
                "topic_name": pending["topic_name"],
                "passed": passed,
            },
        )
    verdict = "**Pass**" if passed else "**Not yet**"
    return {
        "ok": True,
        "handled": True,
        "passed": passed,
        "message": clip(
            f"{verdict} · **{pending['topic_name']}**\n\n"
            f"{feedback}\n\n"
            "`/drill` another question · `/interview-ready` for coverage"
        ),
    }


def interview_ready(*, guild_id: str, asker_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        course = get_active_course_for_guild(conn, guild_id)
        if not course:
            return {"ok": False, "message": "No active course for this server."}
        topics = fetch_syllabus_topics(conn, course["id"])
        stats = {str(r["topic_id"]): r for r in fetch_drill_stats(conn, course_id=course["id"], asker_id=asker_id)}
        insert_agent_action(
            conn,
            course_id=course["id"],
            action_type="interview_ready",
            input_ref=asker_id,
            output_summary=f"Interview-ready digest for {asker_id}",
            payload={"asker_id": asker_id},
        )

    not_started: list[str] = []
    failing: list[str] = []
    ready: list[str] = []
    for topic in topics:
        row = stats.get(str(topic["id"]))
        name = topic["topic_name"]
        if not row or int(row["attempts"]) == 0:
            not_started.append(name)
        elif int(row["passes"]) == 0 or int(row["fails"]) > int(row["passes"]):
            failing.append(
                f"{name} ({row['fails']} miss / {row['passes']} pass)"
            )
        else:
            ready.append(f"{name} ({row['passes']} pass)")

    ready_flag = not not_started and not failing
    headline = "**Interview-ready: yes**" if ready_flag else "**Interview-ready: not yet**"
    lines = [
        headline,
        "_Personal drill memory — class `/ask` questions do not count._",
        "",
        "**Never drilled (0 questions):**",
    ]
    if not_started:
        lines.extend(f"• {name}" for name in not_started[:10])
    else:
        lines.append("• None")
    lines.extend(["", "**Failing / weak:**"])
    if failing:
        lines.extend(f"• {item}" for item in failing[:8])
    else:
        lines.append("• None")
    lines.extend(["", "**Passing:**"])
    if ready:
        lines.extend(f"• {item}" for item in ready[:8])
    else:
        lines.append("• None yet")
    next_topic = not_started[0] if not_started else (failing[0].split(" (")[0] if failing else None)
    if next_topic:
        lines.extend(["", f"Next: `/drill {next_topic}`"])
    return {"ok": True, "message": clip("\n".join(lines))}


def _pick_weak_topic(topics: list[dict[str, Any]], stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    def key(topic: dict[str, Any]) -> tuple[int, int, int]:
        row = stats.get(str(topic["id"]))
        if not row or int(row["attempts"]) == 0:
            return (0, 0, 0)
        fails = int(row["fails"])
        passes = int(row["passes"])
        if passes == 0 or fails > passes:
            return (1, -fails, passes)
        return (2, passes, -fails)

    return sorted(topics, key=key)[0]


def _pick_question(topic_name: str, recent: list[str]) -> tuple[str, str]:
    pack = curriculum_for(topic_name) or {}
    bank: list[dict[str, str]] = list(pack.get("quiz") or [])
    recent_set = set(recent)
    for item in bank:
        q = str(item.get("q") or "").strip()
        if q and q not in recent_set:
            return q, str(item.get("hint") or "")
    if bank:
        item = bank[len(recent) % len(bank)]
        return str(item.get("q") or "Explain this topic as if in a phone screen."), str(item.get("hint") or "")
    return (
        f"In an interview, how would you explain **{topic_name}** and give one example?",
        "Name the idea, give a small example, mention time/space.",
    )


def _score_attempt(*, question: str, hint: str, attempt: str, topic_name: str) -> tuple[bool, str]:
    prompt = f"""You are a FAANG-style phone-screen interviewer for {topic_name}.

Question:
{question}

Candidate answer:
{attempt[:2000]}

Grounding hint (do not quote unless they missed it): {hint}

Return ONLY JSON:
{{
  "passed": true or false,
  "feedback": "3-6 sentences. What was solid, what was missing, how to say it in an interview. Discord markdown ok."
}}
passed=true if a hiring interviewer would move them forward, not only if perfect.
"""
    try:
        data = parse_json_object(invoke_chat(prompt, max_tokens=450, temperature=0.2))
        passed = bool(data.get("passed"))
        feedback = str(data.get("feedback") or "").strip()
        if feedback:
            return passed, feedback
    except Exception as exc:
        logger.warning("Live drill scoring unavailable (%s); using rule fallback", exc)
    return _rule_score(hint=hint, attempt=attempt)


def _rule_score(*, hint: str, attempt: str) -> tuple[bool, str]:
    if len(attempt) < 20:
        return False, "Too short for an interview answer. Walk through the idea in a few sentences, then Big-O."
    hint_tokens = tokenize(hint)
    got = tokenize(attempt)
    if hint_tokens and len(hint_tokens & got) >= max(1, len(hint_tokens) // 4):
        return True, "You hit the key idea. In an interview, say the approach, then complexity, then one edge case."
    hint_line = f" Hint: {hint}" if hint else ""
    return False, f"Not enough of the core idea yet.{hint_line} Try `/drill` on this topic again."
