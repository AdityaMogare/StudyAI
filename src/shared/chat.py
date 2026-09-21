"""Chat providers: OpenAI first, Bedrock fallback, or off (static tutor pack)."""

from __future__ import annotations

import json
import logging

import requests

from shared.config import get_settings

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


def invoke_chat(
    prompt: str,
    *,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> str:
    """Dispatch to CHAT_PROVIDER. auto/openai try OpenAI then Bedrock."""
    settings = get_settings()
    if settings.chat_provider == "off":
        raise RuntimeError("CHAT_PROVIDER=off")

    errors: list[str] = []
    for name in _provider_order(settings):
        try:
            if name == "openai":
                text = _invoke_openai(
                    prompt, max_tokens=max_tokens, temperature=temperature
                )
            else:
                text = _invoke_bedrock(
                    prompt, max_tokens=max_tokens, temperature=temperature
                )
            if text.strip():
                return text
            errors.append(f"{name}: empty response")
        except Exception as exc:
            logger.warning("%s chat failed (%s)", name, exc)
            errors.append(f"{name}: {exc}")
    raise RuntimeError("All chat providers failed: " + "; ".join(errors))


def _provider_order(settings) -> list[str]:
    provider = settings.chat_provider
    has_openai = bool(settings.openai_api_key)
    if provider == "bedrock":
        return ["bedrock"]
    if provider == "openai":
        return ["openai", "bedrock"] if has_openai else ["bedrock"]
    # auto
    if has_openai:
        return ["openai", "bedrock"]
    return ["bedrock"]


def _invoke_openai(
    prompt: str,
    *,
    max_tokens: int,
    temperature: float,
) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    response = requests.post(
        OPENAI_CHAT_URL,
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.openai_chat_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        timeout=45,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"OpenAI HTTP {response.status_code}: {response.text[:300]}"
        )
    payload = response.json()
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError(f"OpenAI returned no choices: {list(payload.keys())}")
    message = (choices[0].get("message") or {}).get("content") or ""
    return str(message).strip()


def _invoke_bedrock(
    prompt: str,
    *,
    max_tokens: int,
    temperature: float,
) -> str:
    from shared.bedrock import converse_chat

    return converse_chat(prompt, max_tokens=max_tokens, temperature=temperature)
