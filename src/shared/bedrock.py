"""Amazon Bedrock helpers for embeddings, Claude extraction, and agent reasoning."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import boto3

from shared.config import get_settings

logger = logging.getLogger(__name__)


def _client():
    settings = get_settings()
    return boto3.client("bedrock-runtime", region_name=settings.aws_region)


def embed_text(text: str) -> list[float]:
    """Generate a 1536-d embedding via Amazon Titan Embed Text v1."""
    settings = get_settings()
    body = json.dumps({"inputText": text})
    response = _client().invoke_model(
        modelId=settings.bedrock_embedding_model,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    payload = json.loads(response["body"].read())
    embedding = payload.get("embedding")
    if not embedding:
        raise RuntimeError(f"No embedding in Bedrock response: {payload.keys()}")
    return embedding


def is_likely_question(text: str) -> bool:
    """Lightweight heuristic filter before embedding spend."""
    cleaned = text.strip()
    if len(cleaned) < 12:
        return False
    if cleaned.startswith(("!", "/", ".")):
        return False
    question_marks = "?" in cleaned
    starters = (
        "what",
        "why",
        "how",
        "when",
        "where",
        "which",
        "who",
        "can ",
        "could ",
        "should ",
        "is ",
        "are ",
        "does ",
        "do ",
        "did ",
        "help",
        "explain",
        "confused",
        "don't understand",
        "dont understand",
    )
    lower = cleaned.lower()
    return question_marks or lower.startswith(starters) or any(
        phrase in lower for phrase in ("anyone know", "i don't get", "i dont get", "stuck on")
    )


def extract_topics_from_syllabus(syllabus_text: str) -> list[dict[str, str]]:
    """Use Claude on Bedrock to extract distinct syllabus topics as JSON."""
    prompt = f"""Extract distinct exam-relevant topics from this course syllabus.

Return ONLY a JSON array. Each item must have:
- "topic_name": short title
- "description": 1-2 sentence summary of what students must know

Syllabus:
---
{syllabus_text[:20000]}
---
"""
    text = invoke_claude(prompt, max_tokens=4096, temperature=0.2)
    return _parse_json_array(text)


def invoke_claude(
    prompt: str,
    *,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> str:
    settings = get_settings()
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = _client().invoke_model(
        modelId=settings.bedrock_chat_model,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )
    payload = json.loads(response["body"].read())
    return _claude_text(payload)


def recommend_ta_interventions(
    *,
    course_name: str,
    untouched: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    recent_questions: list[str] | None = None,
) -> dict[str, Any]:
    """Claude acts on coverage memory: prioritize what TAs should teach next."""
    untouched_names = [r["topic_name"] for r in untouched[:20]]
    unresolved_lines = [
        f"{r['topic_name']} (open={r['open_count']}, total={r['question_count']})"
        for r in unresolved[:20]
    ]
    recent = recent_questions or []
    prompt = f"""You are StudyAI, a classroom memory agent for "{course_name}".

Using durable coverage memory from CockroachDB, recommend TA actions before the exam.

Untouched topics (zero student questions):
{json.dumps(untouched_names)}

Unresolved clusters (many open questions):
{json.dumps(unresolved_lines)}

Recent student questions (sample):
{json.dumps(recent[:10])}

Return ONLY JSON with:
{{
  "priority_topics": ["topic names in teaching order, max 5"],
  "office_hours_focus": "1-2 sentence plan",
  "exam_risk": "low|medium|high",
  "rationale": "2-3 sentences citing the memory signals"
}}
"""
    text = invoke_claude(prompt, max_tokens=1024, temperature=0.3)
    try:
        return _parse_json_object(text)
    except ValueError:
        logger.warning("Failed to parse TA recommendation JSON; using fallback")
        return {
            "priority_topics": untouched_names[:3] or [r["topic_name"] for r in unresolved[:3]],
            "office_hours_focus": "Review untouched and high-open topics from the gap report.",
            "exam_risk": "medium" if (untouched or unresolved) else "low",
            "rationale": text[:500],
        }


def _claude_text(payload: dict[str, Any]) -> str:
    content = payload.get("content") or []
    parts = [block.get("text", "") for block in content if block.get("type") == "text"]
    return "\n".join(parts).strip()


def _parse_json_array(text: str) -> list[dict[str, str]]:
    cleaned = _strip_fence(text)
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"Claude did not return a JSON array: {text[:400]}")
    data = json.loads(cleaned[start : end + 1])
    topics: list[dict[str, str]] = []
    for item in data:
        name = str(item.get("topic_name", "")).strip()
        desc = str(item.get("description", "")).strip()
        if name:
            topics.append({"topic_name": name, "description": desc})
    if not topics:
        raise ValueError("No topics parsed from Claude response")
    return topics


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_fence(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Claude did not return a JSON object: {text[:400]}")
    data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object")
    return data


def _strip_fence(text: str) -> str:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fenced:
        return fenced.group(1).strip()
    return cleaned
