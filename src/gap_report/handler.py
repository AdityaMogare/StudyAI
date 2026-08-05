"""Weekly Gap Report Lambda — EventBridge cron → Discord embed."""

from __future__ import annotations

import json
import logging
from typing import Any

from shared.config import get_settings
from shared.gap_logic import build_and_post_gap_report

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    settings = get_settings()
    guild_id = (event or {}).get("guild_id") or settings.discord_guild_id
    channel_id = (event or {}).get("channel_id") or settings.report_channel_id

    result = build_and_post_gap_report(guild_id=guild_id, channel_id=channel_id)
    logger.info("Gap report result: %s", result)
    status = 200 if result.get("ok") else 500
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(result),
    }
