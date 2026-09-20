"""Exam-prep tutor loop on top of classroom memory."""

from __future__ import annotations

import logging
import re
from typing import Any

from shared.agent import format_memory_digest, link_question_to_topics
from shared.bedrock import embed_text, invoke_chat, parse_json_object
from shared.config import get_settings
from shared.cs101_tutor import curriculum_for, match_topic_name
from shared.db import (
    count_live_tutor_answers_today,
    fetch_learner_coverage,
    fetch_syllabus_topics,
    fetch_topic_question_texts,
    get_active_course_for_guild,
    get_conn,
    insert_agent_action,
    insert_answer,
    insert_question,
)

logger = logging.getLogger(__name__)

TUTOR_RESPONDER_ID = "studyai-tutor"
DISCORD_LIMIT = 1900


def _clean_question(text: str) -> str:
    return re.sub(r"<[#@&!]?\d+>", "", text or "").strip()


def clip(text: str, limit: int = DISCORD_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n… _(truncated)_"


def _static_pack(topic_name: str | None) -> dict[str, Any]:
    pack = curriculum_for(topic_name)
    if pack:
        return {
            "explanation": str(pack["explanation"]),
            "followups": list(pack["followups"])[:2],
        }
    return {
        "explanation": (
            "I stored your question in course memory, but it did not match a syllabus "
            "topic closely. Start by naming the structure or algorithm involved, then "
            "try `/quiz` on that topic."
        ),
        "followups": [
            "Restate the problem in one sentence and name the CS 101 topic.",
            "Try a 3-item example by hand before writing code.",
        ],
    }


def _live_tutor(*, question_text: str, topic_name: str | None) -> dict[str, Any] | None:
    settings = get_settings()
    if settings.chat_mode == "off":
        return None
    pack = curriculum_for(topic_name) or {}
    notes = str(pack.get("explanation") or "")
    prompt = f"""You are StudyAI, a CS 101 exam/interview tutor.

Answer THIS student's question directly (do not paste a generic topic summary).
Use the curriculum notes only as grounding. Prefer a short worked example.

Topic: {topic_name or "General CS 101"}
Curriculum notes:
{notes}

Student question:
{question_text[:1500]}

Return ONLY JSON:
{{
  "explanation": "4-8 sentences, Discord markdown (**bold** ok). Address the question.",
  "followups": [
    "plain string: interview-style drill that checks the same idea",
    "plain string: harder follow-up (edge case, complexity, or what you would say in an interview)"
  ]
}}
"""
    try:
        raw = invoke_chat(prompt, max_tokens=700, temperature=0.35)
        data = parse_json_object(raw)
    except Exception as exc:
        logger.warning("Live tutor unavailable (%s); using static pack", exc)
        return None
    explanation = str(data.get("explanation") or "").strip()
    followups = [_followup_text(item) for item in (data.get("followups") or [])]
    followups = [item for item in followups if item]
    if not explanation:
        return None
    if len(followups) < 2:
        followups.extend(_static_pack(topic_name)["followups"])
    return {"explanation": explanation, "followups": followups[:2]}


def _followup_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("question", "q", "prompt", "text"):
            value = str(item.get(key) or "").strip()
            if value:
                return value
        return " ".join(str(v).strip() for v in item.values() if str(v).strip())
    return str(item or "").strip()


def _cap_footer(*, source: str, used: int, cap: int) -> str:
    if cap <= 0:
        return "_Live answer_" if source == "live" else "_Static CS 101 pack_"
    if source == "live":
        return f"_Live answer · {used}/{cap} today_"
    if used >= cap:
        return f"_Static pack — live cap {cap}/{cap} resets at UTC midnight._"
    return "_Static CS 101 pack (live tutor unavailable)._"


def build_explanation(
    *,
    question_text: str,
    topic_name: str | None,
    live_used_today: int = 0,
) -> dict[str, Any]:
    settings = get_settings()
    cap = settings.tutor_daily_cap
    over_cap = cap > 0 and live_used_today >= cap
    live = None if over_cap else _live_tutor(
        question_text=question_text, topic_name=topic_name
    )
    pack = live or _static_pack(topic_name)
    source = "live" if live else "static"
    used_after = live_used_today + 1 if source == "live" else live_used_today
    return {
        "topic_name": topic_name,
        "explanation": pack["explanation"],
        "followups": pack["followups"],
        "source": source,
        "message": _format_tutor_message(
            question_text,
            topic_name,
            pack["explanation"],
            pack["followups"],
            footer=_cap_footer(source=source, used=used_after, cap=cap),
        ),
    }


def _format_tutor_message(
    question_text: str,
    topic_name: str | None,
    explanation: str,
    followups: list[str],
    *,
    footer: str = "",
) -> str:
    topic_line = f"**{topic_name}**" if topic_name else "**General CS 101**"
    lines = [
        topic_line,
        explanation,
        "",
        f"_You asked:_ {question_text[:240]}",
        "",
        "**Interview / drill:**",
    ]
    for i, item in enumerate(followups[:2], 1):
        lines.append(f"{i}. {item}")
    lines.append("")
    if footer:
        lines.append(footer)
    lines.append("React ✅ when this clicks. `/quiz` drills the topic · `/weak-spots` · `/plan`")
    return clip("\n".join(lines))


def capture_question(
    *,
    guild_id: str,
    channel_id: str,
    message_id: str,
    asker_id: str,
    question_text: str,
) -> dict[str, Any]:
    embedding = embed_text(question_text)
    with get_conn() as conn:
        course = get_active_course_for_guild(conn, guild_id)
        if not course:
            return {
                "ok": False,
                "error": "no_active_course",
                "message": "No active course for this server. Seed a syllabus first.",
            }
        row = insert_question(
            conn,
            course_id=course["id"],
            channel_id=channel_id,
            message_id=message_id,
            asker_id=asker_id,
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
        topic_name = matches[0]["topic_name"] if matches else None
        live_used = count_live_tutor_answers_today(
            conn, course_id=course["id"], asker_id=asker_id
        )
        taught = build_explanation(
            question_text=question_text,
            topic_name=topic_name,
            live_used_today=live_used,
        )
        insert_answer(
            conn,
            question_id=row["id"],
            message_id=f"tutor-{row['id']}",
            responder_id=TUTOR_RESPONDER_ID,
            answer_text=taught["explanation"],
        )
        insert_agent_action(
            conn,
            course_id=course["id"],
            action_type="tutor_answer",
            input_ref=str(row["id"]),
            output_summary=f"Tutored {topic_name or 'unmatched'} for asker {asker_id}",
            payload={
                "topic_name": topic_name,
                "followups": taught["followups"],
                "asker_id": asker_id,
                "source": taught.get("source", "static"),
            },
        )
    topics = [m["topic_name"] for m in matches]
    return {
        "ok": True,
        "question_id": str(row["id"]),
        "linked_topics": topics,
        "topic_name": topic_name,
        "followups": taught["followups"],
        "message": taught["message"],
    }


def quiz_topic(*, guild_id: str, topic_query: str | None, asker_id: str = "") -> dict[str, Any]:
    with get_conn() as conn:
        course = get_active_course_for_guild(conn, guild_id)
        if not course:
            return {"ok": False, "message": "No active course for this server."}
        topics = fetch_syllabus_topics(conn, course["id"])
        names = [t["topic_name"] for t in topics]
        coverage = fetch_learner_coverage(conn, course["id"], asker_id=asker_id)
        chosen = match_topic_name(topic_query or "", names) if topic_query else None
        if not chosen:
            weak = [r for r in coverage if int(r["mine_count"]) == 0]
            chosen = (weak[0]["topic_name"] if weak else names[0]) if names else None
        if not chosen:
            return {"ok": False, "message": "No syllabus topics to quiz."}
        topic_row = next((t for t in topics if t["topic_name"] == chosen), topics[0])
        past = fetch_topic_question_texts(
            conn, course_id=course["id"], topic_id=topic_row["id"], limit=8
        )
        pack = curriculum_for(chosen) or {}
        bank: list[str] = [item["q"] for item in pack.get("quiz") or []]
        class_qs = [_clean_question(p) for p in past if p not in bank]
        mixed: list[str] = []
        for item in class_qs[:2] + bank:
            if item not in mixed:
                mixed.append(item)
            if len(mixed) >= 5:
                break
        insert_agent_action(
            conn,
            course_id=course["id"],
            action_type="quiz",
            input_ref=str(topic_row["id"]),
            output_summary=f"Quiz on {chosen} ({len(mixed)} items)",
            payload={"topic": chosen, "asker_id": asker_id, "count": len(mixed)},
        )

    if not mixed:
        return {
            "ok": True,
            "message": clip(f"No quiz items yet for **{chosen}**. Ask a question first, then retry."),
        }
    lines = [
        f"**Quiz · {chosen}**",
        "_Answer in the channel. Class questions are mixed in when we have them._",
        "",
    ]
    for i, q in enumerate(mixed[:5], 1):
        lines.append(f"**{i}.** {q}")
    hint_pack = curriculum_for(chosen)
    if hint_pack and hint_pack.get("quiz"):
        lines.append("")
        lines.append("_Hints available — ask if you get stuck, then `/ask` the ones you miss._")
    return {"ok": True, "topic_name": chosen, "message": clip("\n".join(lines))}


def weak_spots(*, guild_id: str, asker_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        course = get_active_course_for_guild(conn, guild_id)
        if not course:
            return {"ok": False, "message": "No active course for this server."}
        rows = fetch_learner_coverage(conn, course["id"], asker_id=asker_id)
        insert_agent_action(
            conn,
            course_id=course["id"],
            action_type="weak_spots",
            input_ref=asker_id,
            output_summary=f"Weak-spot digest for {asker_id}",
            payload={"asker_id": asker_id},
        )

    personal = [r for r in rows if int(r["mine_count"]) == 0]
    class_untouched = [r for r in rows if int(r["question_count"]) == 0]
    explained = [r for r in rows if int(r["explained_count"]) > 0]
    open_hot = sorted(
        [r for r in rows if int(r["open_count"]) >= 1],
        key=lambda r: int(r["open_count"]),
        reverse=True,
    )
    lines = [
        f"**Weak spots · {course['course_name']}**",
        f"You have asked about {len(rows) - len(personal)}/{len(rows)} topics.",
        "",
        "**You have never asked about:**",
    ]
    if personal:
        lines.extend(f"• {r['topic_name']}" for r in personal[:8])
    else:
        lines.append("• None — you have touched every syllabus topic.")
    lines.extend(["", "**Class still has no questions on:**"])
    if class_untouched:
        lines.extend(f"• {r['topic_name']}" for r in class_untouched[:8])
    else:
        lines.append("• None — every topic has at least one question.")
    if open_hot:
        lines.extend(["", "**Still open in class:**"])
        lines.extend(
            f"• {r['topic_name']} ({r['open_count']} open)" for r in open_hot[:5]
        )
    if explained:
        lines.extend(
            [
                "",
                f"_Explained in memory:_ {len(explained)} topics have a stored tutor/TA answer.",
            ]
        )
    lines.append("")
    lines.append("Next: `/quiz` on a gap, or `/plan` for this week.")
    return {"ok": True, "message": clip("\n".join(lines))}


def weekly_plan(*, guild_id: str, asker_id: str = "") -> dict[str, Any]:
    with get_conn() as conn:
        course = get_active_course_for_guild(conn, guild_id)
        if not course:
            return {"ok": False, "message": "No active course for this server."}
        rows = fetch_learner_coverage(conn, course["id"], asker_id=asker_id)
        personal_gaps = [r["topic_name"] for r in rows if int(r["mine_count"]) == 0]
        class_gaps = [r["topic_name"] for r in rows if int(r["question_count"]) == 0]
        review = [
            r["topic_name"]
            for r in rows
            if int(r["explained_count"]) > 0 and int(r["open_count"]) > 0
        ]
        insert_agent_action(
            conn,
            course_id=course["id"],
            action_type="study_plan",
            input_ref=str(course["id"]),
            output_summary="Weekly exam study plan",
            payload={
                "personal_gaps": personal_gaps[:8],
                "class_gaps": class_gaps[:8],
            },
        )

    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    agenda = (class_gaps or personal_gaps or [r["topic_name"] for r in rows])[:5]
    while len(agenda) < 5 and rows:
        name = rows[len(agenda) % len(rows)]["topic_name"]
        if name not in agenda:
            agenda.append(name)
        else:
            break
    lines = [
        f"**This week’s exam plan · {course['course_name']}**",
        "Grounded in classroom memory (what nobody asked + what you skipped).",
        "",
    ]
    for day, topic in zip(days, agenda):
        lines.append(f"**{day}** — {topic} · `/quiz {topic}`")
    if review:
        lines.extend(["", "**Revisit (asked but still open):**"])
        lines.extend(f"• {name}" for name in review[:4])
    lines.extend(
        [
            "",
            f"Personal gaps: {len(personal_gaps)} · Class untouched: {len(class_gaps)}",
            "Use `/ask` when stuck. ✅ when a topic is solid.",
        ]
    )
    return {"ok": True, "message": clip("\n".join(lines))}


def memory_digest(guild_id: str, *, asker_id: str = "") -> dict[str, Any]:
    with get_conn() as conn:
        course = get_active_course_for_guild(conn, guild_id)
        if not course:
            return {
                "ok": False,
                "error": "no_active_course",
                "message": "No active course memory for this server.",
            }
        coverage = fetch_learner_coverage(conn, course["id"], asker_id=asker_id)
        digest = format_memory_digest(
            conn,
            course_id=course["id"],
            course_name=course["course_name"],
        )

    untouched = [r for r in coverage if int(r["question_count"]) == 0]
    explained = [r for r in coverage if int(r["explained_count"]) > 0]
    still_open = [r for r in coverage if int(r["open_count"]) > 0]
    extra = [
        "",
        f"**Explained (tutor/TA answer stored):** {len(explained)}/{len(coverage)} topics",
        f"**Still open:** {len(still_open)} · **Never asked:** {len(untouched)}",
        "",
        "Students: `/plan` this week · `/weak-spots` · `/quiz`",
    ]
    return {"ok": True, "message": clip(digest + "\n" + "\n".join(extra))}
