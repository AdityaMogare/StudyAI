"""Environment configuration for StudyAI."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    aws_region: str
    bedrock_embedding_model: str
    bedrock_chat_model: str
    embedding_mode: str
    chat_mode: str
    tutor_daily_cap: int
    local_mode: bool
    sqlite_path: str
    discord_bot_token: str
    discord_public_key: str
    discord_application_id: str
    discord_guild_id: str
    questions_channel_ids: list[str]
    report_channel_id: str
    similarity_threshold: float

    @classmethod
    def from_env(cls) -> Settings:
        database_url = os.environ.get("DATABASE_URL", "").strip()
        sqlite_path = os.environ.get("SQLITE_PATH", "data/studyai.db").strip() or "data/studyai.db"
        local_mode = _truthy(os.environ.get("LOCAL_MODE")) or database_url.startswith("sqlite")
        embedding_mode = os.environ.get("EMBEDDING_MODE", "auto").strip().lower()
        if local_mode and embedding_mode == "auto":
            embedding_mode = "local"
        chat_mode = os.environ.get("CHAT_MODE", "auto").strip().lower()
        if chat_mode not in {"auto", "bedrock", "off"}:
            chat_mode = "auto"
        try:
            tutor_daily_cap = int(os.environ.get("TUTOR_DAILY_CAP", "20").strip() or "20")
        except ValueError:
            tutor_daily_cap = 20
        if not local_mode and not database_url:
            raise KeyError("DATABASE_URL is required unless LOCAL_MODE=true")
        return cls(
            database_url=database_url,
            aws_region=os.environ.get("AWS_REGION", "us-east-1"),
            bedrock_embedding_model=os.environ.get(
                "BEDROCK_EMBEDDING_MODEL", "amazon.titan-embed-text-v1"
            ),
            bedrock_chat_model=os.environ.get(
                "BEDROCK_CHAT_MODEL", "mistral.ministral-3-8b-instruct"
            ),
            embedding_mode=embedding_mode,
            chat_mode=chat_mode,
            tutor_daily_cap=max(0, tutor_daily_cap),
            local_mode=local_mode,
            sqlite_path=sqlite_path,
            discord_bot_token=os.environ.get("DISCORD_BOT_TOKEN", ""),
            discord_public_key=os.environ.get("DISCORD_PUBLIC_KEY", ""),
            discord_application_id=os.environ.get("DISCORD_APPLICATION_ID", ""),
            discord_guild_id=os.environ.get("DISCORD_GUILD_ID", ""),
            questions_channel_ids=_split_csv(os.environ.get("QUESTIONS_CHANNEL_IDS")),
            report_channel_id=os.environ.get("REPORT_CHANNEL_ID", ""),
            similarity_threshold=float(os.environ.get("SIMILARITY_THRESHOLD", "0.3")),
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def reset_settings() -> None:
    """Clear cached settings (useful after env changes in long-lived processes)."""
    global _settings
    _settings = None
