#!/usr/bin/env python3
"""Print the OAuth invite URL for the Discord app in .env."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from shared.discord_api import bot_invite_url  # noqa: E402


def main() -> int:
    app_id = os.environ.get("DISCORD_APPLICATION_ID", "").strip()
    if not app_id:
        print("DISCORD_APPLICATION_ID is required", file=sys.stderr)
        return 1
    url = bot_invite_url(app_id)
    print("Invite the StudyAI bot into your existing server with this URL:")
    print(url)
    print()
    print("Pick the StudyAI server → Authorize.")
    print("Then run: make discord-local")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
