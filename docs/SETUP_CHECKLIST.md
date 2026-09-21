# Setup checklist — get StudyAI APIs live

Complete these before demo day. Do **not** commit real secrets.

Prefer **local-first** ([LOCAL_DEV.md](LOCAL_DEV.md)) if SAM/Bedrock is not ready.

## 0. Local Discord only (no AWS, no Cockroach)

Use this to try `/ask`, `/quiz`, `/weak-spots`, `/plan`, `/memory`, `/gap-report`, `/resolved` on your laptop.

1. Discord app + bot in your server (Message Content Intent **on**).
2. Leave **Interactions Endpoint URL empty** so slash commands go to the local process.
3. In `.env`: `LOCAL_MODE=true`, bot token, application id, guild id, channel ids. Optional: `CHAT_PROVIDER=auto`, `OPENAI_API_KEY`, and `TUTOR_DAILY_CAP=20` for live `/ask` (OpenAI first, Bedrock fallback, then the static CS 101 pack).
4. Invite **this** app into the server (creating the Discord app does not add the bot):

```bash
make discord-invite
# open the printed URL → pick the StudyAI server → Authorize
```

5. Then:

```bash
python3 -m venv .venv && source .venv/bin/activate
make install
make discord-local
```

The bot seeds CS 101 into `data/studyai.db` on first run. Optional: `LOCAL_MODE=true make smoke`.

## 1. CockroachDB Cloud

- [x] Create Serverless (or Dedicated) cluster
- [x] Create database `studyai`
- [x] Copy SQL connection string → `DATABASE_URL` in `.env`
- [x] Enable / confirm VECTOR support (24.2+; VECTOR INDEX 25.2+)
- [ ] Connect Cursor MCP ([MCP_SETUP.md](MCP_SETUP.md)) and authenticate
- [x] Apply schema:

```bash
export DATABASE_URL='postgresql://...'
make schema          # 001_init.sql
make schema-agent    # 002_agent_memory.sql
```

## 2. AWS + Bedrock

- [ ] AWS account + CLI configured (`aws sts get-caller-identity`)
- [ ] Region set (default `us-east-1`) matching Bedrock model access
- [ ] Enable model access: `amazon.titan-embed-text-v1` (+ chat model if quota allows)
- [ ] SAM CLI installed (`sam --version`)
- [ ] If Bedrock **tokens/day** is blocked: set `EMBEDDING_MODE=auto` (or `local`) and use offline syllabus seed

## 3. Discord application

- [x] Create app at https://discord.com/developers/applications
- [x] Copy **Application ID**, **Public Key**, create **Bot** → token
- [ ] Enable **Message Content Intent**
- [ ] Invite bot to your demo guild (scopes: `bot`, `applications.commands`)
- [x] Create `#questions` and `#exam-prep` (or `#announcements`) channels
- [x] Copy guild + channel IDs into `.env`

## 4. Local `.env`

```bash
cp .env.example .env
# fill all values — never commit .env
# BEDROCK_EMBEDDING_MODEL=amazon.titan-embed-text-v1   # must be 1536-d
# EMBEDDING_MODE=auto                                  # falls back to local vectors
# or EMBEDDING_MODE=local for FastAPI demo without Titan
```

## 5. Local-first (no AWS Lambda)

```bash
make install
make schema && make schema-agent
make seed-syllabus
make smoke
make local
# other terminal: cloudflared tunnel --url http://127.0.0.1:8080
# Discord Interactions URL = https://<tunnel>/interactions
export INGESTION_URL=http://127.0.0.1:8080/ingestion
export RESOLUTION_URL=http://127.0.0.1:8080/interactions
make register
make gateway
make seed          # optional demo questions
make gap-report    # optional CLI report
```

## 6. Deploy SAM + wire Discord (optional later)

```bash
make install
make schema && make schema-agent
# Prefer offline seed when Bedrock chat quota is exhausted:
make seed-syllabus
# Or LLM extract (needs working Bedrock chat):
# python tools/ingest_syllabus.py --file samples/syllabus_cs101.txt \
#   --guild-id "$DISCORD_GUILD_ID" --course-name "CS 101"
sam build && sam deploy --guided
# Set Discord Interactions Endpoint URL to Outputs.InteractionsUrl
make register
export INGESTION_URL=... RESOLUTION_URL=...
make gateway
make seed    # optional demo questions
make smoke   # local ask/link/memory/resolve check
```

## 7. Smoke test

- [ ] `make smoke` passes locally
- [ ] `/ask How does binary search work?` → linked topics reply
- [ ] MCP/SQL: row in `questions` + `question_topic_links` + `agent_actions`
- [ ] `/memory` → TA digest
- [ ] `/gap-report` → embed in report channel (rule-based if Bedrock chat fails)
- [ ] ✅ reaction or `/resolved` → status `resolved`
