#!/usr/bin/env python3
"""Thin Discord gateway relay for passive message + reaction capture.

Discord Interactions (slash commands) hit Lambda via HTTP. MESSAGE_CREATE and
reactions require a Gateway connection — this process forwards those events to
the Ingestion / Resolution API Gateway endpoints.

Usage:
  export DISCORD_BOT_TOKEN=...
  export INGESTION_URL=https://.../ingestion
  export RESOLUTION_URL=https://.../interactions
  export QUESTIONS_CHANNEL_IDS=111,222
  python gateway/relay.py
"""

from __future__ import annotations

import os
import logging

import discord
import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("studyai.gateway")

INGESTION_URL = os.environ.get("INGESTION_URL", "")
RESOLUTION_URL = os.environ.get("RESOLUTION_URL", "")
QUESTIONS_CHANNEL_IDS = {
    c.strip() for c in os.environ.get("QUESTIONS_CHANNEL_IDS", "").split(",") if c.strip()
}
RESOLVE_EMOJI = {"✅", "✔️", "✓"}


class StudyAIRelay(discord.Client):
    async def on_ready(self) -> None:
        logger.info("Logged in as %s — watching %s channels", self.user, QUESTIONS_CHANNEL_IDS or "ALL")

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        if QUESTIONS_CHANNEL_IDS and str(message.channel.id) not in QUESTIONS_CHANNEL_IDS:
            return
        if not INGESTION_URL:
            logger.warning("INGESTION_URL not set; skipping message")
            return

        payload = {
            "guild_id": str(message.guild.id),
            "channel_id": str(message.channel.id),
            "message_id": str(message.id),
            "author_id": str(message.author.id),
            "author_bot": False,
            "content": message.content,
        }
        try:
            resp = requests.post(INGESTION_URL, json=payload, timeout=20)
            logger.info("Ingest %s → %s %s", message.id, resp.status_code, resp.text[:200])
        except requests.RequestException:
            logger.exception("Failed to forward message %s", message.id)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.user_id == (self.user.id if self.user else None):
            return
        if str(payload.emoji) not in RESOLVE_EMOJI and payload.emoji.name not in {
            "white_check_mark",
            "heavy_check_mark",
            "✅",
        }:
            return
        if not RESOLUTION_URL:
            return

        body = {
            "event": "reaction_add",
            "message_id": str(payload.message_id),
            "user_id": str(payload.user_id),
            "channel_id": str(payload.channel_id),
            "guild_id": str(payload.guild_id) if payload.guild_id else "",
            "emoji": {"name": payload.emoji.name},
        }
        try:
            resp = requests.post(RESOLUTION_URL, json=body, timeout=20)
            logger.info("Resolve react %s → %s", payload.message_id, resp.status_code)
        except requests.RequestException:
            logger.exception("Failed to forward reaction")


def main() -> None:
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN is required")

    intents = discord.Intents.default()
    intents.message_content = True
    intents.reactions = True
    intents.guilds = True
    client = StudyAIRelay(intents=intents)
    client.run(token)


if __name__ == "__main__":
    main()
