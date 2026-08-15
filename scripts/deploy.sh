#!/usr/bin/env bash
# Guided deploy helper for StudyAI (requires AWS SAM CLI + filled .env)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.example and fill credentials first."
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

echo "Building SAM application..."
sam build

echo "Deploying (guided if no samconfig yet)..."
if [[ -f samconfig.toml ]]; then
  sam deploy
else
  sam deploy --guided \
    --parameter-overrides \
    "DatabaseUrl=${DATABASE_URL}" \
    "DiscordBotToken=${DISCORD_BOT_TOKEN}" \
    "DiscordPublicKey=${DISCORD_PUBLIC_KEY}" \
    "DiscordApplicationId=${DISCORD_APPLICATION_ID}" \
    "DiscordGuildId=${DISCORD_GUILD_ID}" \
    "QuestionsChannelIds=${QUESTIONS_CHANNEL_IDS}" \
    "ReportChannelId=${REPORT_CHANNEL_ID}"
fi

echo ""
echo "Next:"
echo "  1. Copy Outputs.InteractionsUrl → Discord Interactions Endpoint URL"
echo "  2. make register"
echo "  3. export INGESTION_URL=... RESOLUTION_URL=... && make gateway"
echo "See docs/SETUP_CHECKLIST.md"
