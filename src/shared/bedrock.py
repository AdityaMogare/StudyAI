"""Amazon Bedrock helpers for embeddings and Claude topic extraction."""

from __future__ import annotations

import json
import re
from typing import Any

import boto3

from shared.config import get_settings


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
    settings = get_settings()
    prompt = f"""Extract distinct exam-relevant topics from this course syllabus.

Return ONLY a JSON array. Each item must have:
- "topic_name": short title
- "description": 1-2 sentence summary of what students must know

Syllabus:
---
{syllabus_text[:20000]}
---
"""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = _client().invoke_model(
        modelId=settings.bedrock_chat_model,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )
    payload = json.loads(response["body"].read())
    text = _claude_text(payload)
    return _parse_json_array(text)


def _claude_text(payload: dict[str, Any]) -> str:
    content = payload.get("content") or []
    parts = [block.get("text", "") for block in content if block.get("type") == "text"]
    return "\n".join(parts).strip()


def _parse_json_array(text: str) -> list[dict[str, str]]:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fenced:
        cleaned = fenced.group(1).strip()
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
