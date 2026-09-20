"""Amazon Bedrock helpers for embeddings, chat extraction, and agent reasoning."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import struct
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.config import get_settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536


def _client():
    settings = get_settings()
    return boto3.client("bedrock-runtime", region_name=settings.aws_region)


def local_embed_text(text: str, *, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic 1536-d embedding for demos when Bedrock is unavailable.

    Same text always yields the same vector so VECTOR nearest-neighbor still works
    within a locally-embedded corpus. Quality is lower than Titan.
    """
    digest = hashlib.sha256(text.strip().encode("utf-8")).digest()
    values: list[float] = []
    counter = 0
    while len(values) < dim:
        block = hashlib.sha256(digest + counter.to_bytes(4, "big")).digest()
        for i in range(0, len(block) - 3, 4):
            raw = struct.unpack_from(">I", block, i)[0]
            values.append((raw / 0xFFFFFFFF) * 2.0 - 1.0)
            if len(values) >= dim:
                break
        counter += 1
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def embed_text(text: str) -> list[float]:
    """Generate a 1536-d embedding via Titan, with optional local fallback."""
    settings = get_settings()
    mode = settings.embedding_mode
    if mode == "local":
        return local_embed_text(text)

    try:
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
        if len(embedding) != EMBEDDING_DIM:
            raise RuntimeError(
                f"Expected {EMBEDDING_DIM}-d embedding for schema, got {len(embedding)}. "
                "Use amazon.titan-embed-text-v1 (or change VECTOR size)."
            )
        return embedding
    except Exception as exc:
        if mode == "bedrock":
            raise
        logger.warning("Bedrock embedding failed (%s); using local fallback", exc)
        return local_embed_text(text)


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
    """Use Bedrock chat to extract distinct syllabus topics as JSON."""
    prompt = f"""Extract distinct exam-relevant topics from this course syllabus.

Return ONLY a JSON array. Each item must have:
- "topic_name": short title
- "description": 1-2 sentence summary of what students must know

Syllabus:
---
{syllabus_text[:12000]}
---
"""
    text = invoke_chat(prompt, max_tokens=2048, temperature=0.2)
    return _parse_json_array(text)


def invoke_chat(
    prompt: str,
    *,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> str:
    """Call Bedrock Converse (works for Mistral, Nova, Claude, Llama)."""
    settings = get_settings()
    if settings.chat_mode == "off":
        raise RuntimeError("CHAT_MODE=off")
    try:
        response = _client().converse(
            modelId=settings.bedrock_chat_model,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        msg = exc.response.get("Error", {}).get("Message", str(exc))
        if code == "ThrottlingException":
            raise RuntimeError(
                f"Bedrock quota hit for {settings.bedrock_chat_model}: {msg}. "
                "Use offline syllabus seed or wait for tokens/day reset."
            ) from exc
        raise
    return _converse_text(response)


def invoke_claude(
    prompt: str,
    *,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> str:
    """Backward-compatible alias for invoke_chat."""
    return invoke_chat(prompt, max_tokens=max_tokens, temperature=temperature)


def _rule_based_recommendations(
    untouched: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
) -> dict[str, Any]:
    untouched_names = [r["topic_name"] for r in untouched[:20]]
    unresolved_names = [r["topic_name"] for r in unresolved[:20]]
    priority = (untouched_names[:3] + unresolved_names[:3])[:5]
    risk = "high" if len(untouched) >= 3 or len(unresolved) >= 2 else (
        "medium" if untouched or unresolved else "low"
    )
    return {
        "priority_topics": priority,
        "office_hours_focus": (
            "Cover untouched syllabus topics first, then open question clusters "
            "with the highest open counts."
        ),
        "exam_risk": risk,
        "rationale": (
            f"Rule-based plan from classroom coverage memory: "
            f"{len(untouched)} untouched topics, {len(unresolved)} unresolved clusters."
        ),
    }


def recommend_ta_interventions(
    *,
    course_name: str,
    untouched: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    recent_questions: list[str] | None = None,
) -> dict[str, Any]:
    """Chat model acts on coverage memory; falls back to rule-based plan on failure."""
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
    try:
        text = invoke_chat(prompt, max_tokens=1024, temperature=0.3)
        return _parse_json_object(text)
    except Exception as exc:
        logger.warning("TA recommendation via Bedrock failed (%s); using rule-based plan", exc)
        return _rule_based_recommendations(untouched, unresolved)


def _converse_text(payload: dict[str, Any]) -> str:
    content = payload.get("output", {}).get("message", {}).get("content") or []
    return "\n".join(
        block.get("text", "") for block in content if isinstance(block, dict) and block.get("text")
    ).strip()


def _parse_json_array(text: str) -> list[dict[str, str]]:
    cleaned = _strip_fence(text)
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"Chat model did not return a JSON array: {text[:400]}")
    data = json.loads(cleaned[start : end + 1])
    topics: list[dict[str, str]] = []
    for item in data:
        name = str(item.get("topic_name", "")).strip()
        desc = str(item.get("description", "")).strip()
        if name:
            topics.append({"topic_name": name, "description": desc})
    if not topics:
        raise ValueError("No topics parsed from chat model response")
    return topics


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_fence(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Chat model did not return a JSON object: {text[:400]}")
    data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object")
    return data


def parse_json_object(text: str) -> dict[str, Any]:
    return _parse_json_object(text)


def _strip_fence(text: str) -> str:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fenced:
        return fenced.group(1).strip()
    return cleaned
