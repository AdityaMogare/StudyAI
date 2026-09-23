#!/usr/bin/env python3
"""Local Discord bot — slash commands + channel capture without AWS or CockroachDB.

Requires LOCAL_MODE=true (SQLite + local embeddings). Keep the Discord Developer
Portal Interactions Endpoint URL empty so slash commands arrive on the gateway.

Usage:
  set -a && source .env && set +a
  export LOCAL_MODE=true
  python gateway/local_bot.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

load_dotenv(ROOT / ".env")
os.environ.setdefault("LOCAL_MODE", "true")

from shared.bedrock import embed_text, is_likely_question  # noqa: E402
from shared.config import get_settings, reset_settings  # noqa: E402
from shared.db import (  # noqa: E402
    bulk_insert_topics,
    ensure_course,
    fetch_syllabus_topics,
    get_active_course_for_guild,
    get_conn,
    insert_agent_action,
)
from shared.discord_api import bot_invite_url, fetch_bot_guilds  # noqa: E402
from shared.features import (  # noqa: E402
    capture_question,
    interview_ready,
    mark_resolved,
    memory_digest,
    quiz_topic,
    start_drill,
    submit_drill_attempt,
    weak_spots,
    weekly_plan,
)
from shared.gap_logic import build_and_post_gap_report  # noqa: E402
from seed_syllabus_offline import CS101_TOPICS  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("studyai.local_bot")
RESOLVE_EMOJI = {"✅", "✔️", "✓", "white_check_mark", "heavy_check_mark"}


def _seed_cs101_if_needed(guild_id: str) -> None:
    with get_conn() as conn:
        course = get_active_course_for_guild(conn, guild_id)
        if course:
            logger.info("Using course %s (%s)", course["course_name"], course["id"])
            return
        course = ensure_course(conn, guild_id, "CS 101")
        prepared = []
        for topic in CS101_TOPICS:
            blob = f"{topic['topic_name']}\n{topic['description']}".strip()
            prepared.append((topic["topic_name"], topic["description"], embed_text(blob)))
        count = bulk_insert_topics(conn, course["id"], prepared)
        insert_agent_action(
            conn,
            course_id=course["id"],
            action_type="syllabus_ingest",
            input_ref="gateway/local_bot.py",
            output_summary=f"Local-seeded {count} CS 101 topics",
            payload={"topic_count": count, "mode": "local"},
        )
        logger.info("Seeded %s CS 101 topics into SQLite", count)


def _ensure_interview_topics(guild_id: str) -> None:
    extras = [t for t in CS101_TOPICS if t["topic_name"] == "System Design"]
    with get_conn() as conn:
        course = get_active_course_for_guild(conn, guild_id)
        if not course:
            return
        have = {t["topic_name"] for t in fetch_syllabus_topics(conn, course["id"])}
        prepared = []
        for topic in extras:
            if topic["topic_name"] in have:
                continue
            blob = f"{topic['topic_name']}\n{topic['description']}".strip()
            prepared.append((topic["topic_name"], topic["description"], embed_text(blob)))
        if not prepared:
            return
        count = bulk_insert_topics(conn, course["id"], prepared)
        insert_agent_action(
            conn,
            course_id=course["id"],
            action_type="syllabus_ingest",
            input_ref="gateway/local_bot.py",
            output_summary=f"Added {count} interview topics",
            payload={"topic_count": count, "mode": "interview"},
        )
        logger.info("Added %s interview topics", count)


class StudyAILocalBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        intents.guilds = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        settings = get_settings()
        invite = bot_invite_url(settings.discord_application_id or str(self.application_id or ""))
        try:
            guilds = fetch_bot_guilds(settings.discord_bot_token)
        except Exception:
            logger.exception("Could not list bot guilds")
            guilds = []
        guild_ids = {str(g.get("id")) for g in guilds}
        if settings.discord_guild_id and settings.discord_guild_id not in guild_ids:
            names = ", ".join(f"{g.get('name')} ({g.get('id')})" for g in guilds) or "(none)"
            raise SystemExit(
                "The StudyAI bot is not in that Discord server yet "
                f"(DISCORD_GUILD_ID={settings.discord_guild_id}). "
                f"Servers the bot is in: {names}\n\n"
                "Open this invite while logged into Discord, choose your StudyAI server, Authorize:\n"
                f"  {invite}\n\n"
                "Scopes required: bot + applications.commands. Then run make discord-local again."
            )
        try:
            if settings.discord_guild_id:
                guild = discord.Object(id=int(settings.discord_guild_id))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
            else:
                synced = await self.tree.sync()
        except discord.Forbidden:
            raise SystemExit(
                "Discord rejected slash-command sync (Missing Access).\n"
                "Re-invite the SAME app (the one whose token is in .env) with both scopes:\n"
                f"  {invite}\n"
                "In Developer Portal → your app, leave Interactions Endpoint URL empty "
                "unless you are using AWS."
            ) from None
        logger.info("Synced %s slash commands", len(synced))

    async def on_ready(self) -> None:
        settings = get_settings()
        logger.info(
            "Logged in as %s — local SQLite at %s — watching %s",
            self.user,
            settings.sqlite_path,
            settings.questions_channel_ids or "ALL channels",
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        content = (message.content or "").strip()
        if not content:
            return
        drill = submit_drill_attempt(
            guild_id=str(message.guild.id),
            asker_id=str(message.author.id),
            attempt_text=content,
        )
        if drill.get("handled"):
            await message.reply(drill["message"], mention_author=False)
            return
        settings = get_settings()
        channel_ids = set(settings.questions_channel_ids)
        if channel_ids and str(message.channel.id) not in channel_ids:
            return
        if not is_likely_question(content):
            return
        result = capture_question(
            guild_id=str(message.guild.id),
            channel_id=str(message.channel.id),
            message_id=str(message.id),
            asker_id=str(message.author.id),
            question_text=content,
        )
        if result.get("ok"):
            await message.reply(result["message"], mention_author=False)
        else:
            logger.warning("Ingest skipped: %s", result.get("message"))

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.user_id == (self.user.id if self.user else None):
            return
        name = payload.emoji.name if payload.emoji else ""
        if str(payload.emoji) not in RESOLVE_EMOJI and name not in RESOLVE_EMOJI:
            return
        result = mark_resolved(
            message_id=str(payload.message_id),
            responder_id=str(payload.user_id),
            answer_text="Resolved via ✅ reaction",
            answer_message_id=f"react-{payload.message_id}-{payload.user_id}",
            summary="Resolved via reaction",
        )
        if result.get("ok") and payload.channel_id:
            channel = self.get_channel(payload.channel_id)
            if channel and isinstance(channel, discord.abc.Messageable):
                await channel.send(result["message"])


def _register_commands(bot: StudyAILocalBot) -> None:
    @bot.tree.command(
        name="ask",
        description="Ask a CS 101 question — get an explanation and practice follow-ups",
    )
    @app_commands.describe(question="Your question")
    async def ask(interaction: discord.Interaction, question: str) -> None:
        await interaction.response.defer()
        if not is_likely_question(question) and len(question.strip()) < 8:
            await interaction.followup.send("Please provide a clearer study question.")
            return
        result = capture_question(
            guild_id=str(interaction.guild_id or ""),
            channel_id=str(interaction.channel_id or ""),
            message_id=f"ask-{interaction.id}",
            asker_id=str(interaction.user.id),
            question_text=question.strip(),
        )
        await interaction.followup.send(result["message"])

    @bot.tree.command(name="resolved", description="Mark a student question as resolved")
    @app_commands.describe(
        message_id="Discord message ID of the original question",
        note="Optional short resolution note",
    )
    async def resolved(
        interaction: discord.Interaction,
        message_id: str,
        note: str | None = None,
    ) -> None:
        await interaction.response.defer()
        text = note or "Marked resolved via /resolved"
        result = mark_resolved(
            message_id=message_id.strip(),
            responder_id=str(interaction.user.id),
            answer_text=text,
            answer_message_id=f"slash-{message_id}-{interaction.user.id}",
            summary=f"Resolved via /resolved by {interaction.user.id}",
        )
        await interaction.followup.send(result["message"])

    @bot.tree.command(
        name="memory",
        description="Course memory: explained vs still open vs never asked",
    )
    async def memory(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        result = memory_digest(
            str(interaction.guild_id or ""),
            asker_id=str(interaction.user.id),
        )
        await interaction.followup.send(result["message"])

    @bot.tree.command(
        name="gap-report",
        description="Post this week's exam study plan to the report channel",
    )
    async def gap_report(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        result = build_and_post_gap_report(guild_id=str(interaction.guild_id or ""))
        await interaction.followup.send(result["message"])

    @bot.tree.command(name="quiz", description="5 exam-prep questions for a syllabus topic")
    @app_commands.describe(topic="e.g. Arrays, Recursion, Hash Tables")
    async def quiz(interaction: discord.Interaction, topic: str | None = None) -> None:
        await interaction.response.defer()
        result = quiz_topic(
            guild_id=str(interaction.guild_id or ""),
            topic_query=topic,
            asker_id=str(interaction.user.id),
        )
        await interaction.followup.send(result["message"])

    @bot.tree.command(
        name="weak-spots",
        description="Topics you and the class have not covered",
    )
    async def weak_spots_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        result = weak_spots(
            guild_id=str(interaction.guild_id or ""),
            asker_id=str(interaction.user.id),
        )
        await interaction.followup.send(result["message"])

    @bot.tree.command(
        name="plan",
        description="This week's exam study plan from classroom memory",
    )
    async def plan(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        result = weekly_plan(
            guild_id=str(interaction.guild_id or ""),
            asker_id=str(interaction.user.id),
        )
        await interaction.followup.send(result["message"])

    @bot.tree.command(
        name="drill",
        description="One interview question — reply in chat with your attempt",
    )
    @app_commands.describe(topic="e.g. Arrays, Graphs, System Design")
    async def drill_cmd(interaction: discord.Interaction, topic: str | None = None) -> None:
        await interaction.response.defer()
        result = start_drill(
            guild_id=str(interaction.guild_id or ""),
            asker_id=str(interaction.user.id),
            topic_query=topic,
        )
        await interaction.followup.send(result["message"])

    @bot.tree.command(
        name="interview-ready",
        description="Personal coverage: undrilled and failing topics vs passing",
    )
    async def interview_ready_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        result = interview_ready(
            guild_id=str(interaction.guild_id or ""),
            asker_id=str(interaction.user.id),
        )
        await interaction.followup.send(result["message"])


def main() -> None:
    reset_settings()
    settings = get_settings()
    if not settings.local_mode:
        raise SystemExit("Set LOCAL_MODE=true (this bot is the no-AWS / no-Cockroach path).")
    if not settings.discord_bot_token:
        raise SystemExit("DISCORD_BOT_TOKEN is required")
    if not settings.discord_guild_id:
        raise SystemExit("DISCORD_GUILD_ID is required")

    _seed_cs101_if_needed(settings.discord_guild_id)
    _ensure_interview_topics(settings.discord_guild_id)
    bot = StudyAILocalBot()
    _register_commands(bot)
    logger.info("Starting local Discord bot. Leave Interactions Endpoint URL blank in the Discord portal.")
    bot.run(settings.discord_bot_token)


if __name__ == "__main__":
    main()
