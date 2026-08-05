#!/usr/bin/env python3
"""Register Discord guild slash commands for StudyAI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from shared.discord_api import register_guild_commands  # noqa: E402


def main() -> int:
    app_id = os.environ.get("DISCORD_APPLICATION_ID", "")
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    guild_id = os.environ.get("DISCORD_GUILD_ID", "")
    if not all([app_id, token, guild_id]):
        print(
            "DISCORD_APPLICATION_ID, DISCORD_BOT_TOKEN, and DISCORD_GUILD_ID are required",
            file=sys.stderr,
        )
        return 1
    commands = register_guild_commands(app_id, token, guild_id)
    print(f"Registered {len(commands)} guild commands:")
    for cmd in commands:
        print(f"  /{cmd.get('name')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
