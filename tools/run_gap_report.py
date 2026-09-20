#!/usr/bin/env python3
"""Post a gap report to Discord without EventBridge / Lambda."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from shared.gap_logic import build_and_post_gap_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run StudyAI gap report locally")
    parser.add_argument("--guild-id", default=os.environ.get("DISCORD_GUILD_ID", ""))
    parser.add_argument("--channel-id", default=os.environ.get("REPORT_CHANNEL_ID", ""))
    args = parser.parse_args()
    if not args.guild_id:
        print("DISCORD_GUILD_ID / --guild-id required", file=sys.stderr)
        return 1
    result = build_and_post_gap_report(guild_id=args.guild_id, channel_id=args.channel_id or None)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
