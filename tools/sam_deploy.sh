#!/usr/bin/env bash
# Non-interactive SAM deploy using values from .env
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo ".env missing" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

if [[ ! -d .aws-sam/build ]]; then
  echo "Running sam build..."
  sam build
fi

STACK_NAME="${STACK_NAME:-studyai}"
REGION="${AWS_REGION:-us-east-1}"

sam deploy \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --capabilities CAPABILITY_IAM \
  --resolve-s3 \
  --no-confirm-changeset \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    DatabaseUrl="$DATABASE_URL" \
    DiscordBotToken="$DISCORD_BOT_TOKEN" \
    DiscordPublicKey="$DISCORD_PUBLIC_KEY" \
    DiscordApplicationId="$DISCORD_APPLICATION_ID" \
    DiscordGuildId="$DISCORD_GUILD_ID" \
    QuestionsChannelIds="$QUESTIONS_CHANNEL_IDS" \
    ReportChannelId="$REPORT_CHANNEL_ID" \
    BedrockEmbeddingModel="${BEDROCK_EMBEDDING_MODEL:-amazon.titan-embed-text-v1}" \
    BedrockChatModel="${BEDROCK_CHAT_MODEL:-mistral.ministral-3-8b-instruct}" \
    EmbeddingMode="${EMBEDDING_MODE:-auto}" \
    SimilarityThreshold="${SIMILARITY_THRESHOLD:-0.3}" \
    WeeklyReportSchedule="${WEEKLY_REPORT_CRON:-cron(0 17 ? * FRI *)}"

echo ""
sam list stack-outputs --stack-name "$STACK_NAME" --region "$REGION" || true
echo ""
echo "Next:"
echo "  1. Copy InteractionsUrl → Discord Developer Portal → Interactions Endpoint URL"
echo "  2. export INGESTION_URL=... RESOLUTION_URL=..."
echo "  3. make register && make gateway"
echo "  4. make seed-syllabus && make smoke && make seed"
