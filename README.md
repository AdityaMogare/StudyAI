# StudyAI

Discord bot system that passively captures student questions, maps them to syllabus topics with semantic search on **CockroachDB VECTOR**, tracks resolution, and posts a weekly **gap report** of collective class blind spots.

Remote: [AdityaMogare/StudyAI](https://github.com/AdityaMogare/StudyAI)

## Architecture

```
Discord ──Gateway relay──► API Gateway ──► Ingestion Lambda ──► Bedrock (Titan embed)
                │                                    │
                │                                    ▼
                │                             CockroachDB (VECTOR)
                │                                    ▲
Slash cmds ─────┴──► Interactions Lambda ────────────┤
                                                     │
EventBridge (Fri 5pm UTC) ──► Gap Report Lambda ─────┘
                                     │
                                     ▼
                              Discord #exam-prep embed
```

| Component | Trigger | Role |
|-----------|---------|------|
| **Ingestion Lambda** | `POST /ingestion` | Filter questions → Bedrock embedding → `questions` table |
| **Resolution Lambda** | `POST /interactions` | `/resolved`, `/ask`, `/gap-report`, ✅ reactions |
| **Gap Report Lambda** | EventBridge cron | Query `topic_coverage` → Discord rich embed |
| **Syllabus CLI** | Manual | Claude extracts topics → embeddings → `syllabus_topics` |
| **Gateway relay** | Always-on (local/ECS) | Forwards `MESSAGE_CREATE` + reactions (Discord has no HTTP message webhooks) |

## Tech stack

- **UX:** Discord (slash commands + passive channel capture)
- **Compute:** AWS Lambda + API Gateway + EventBridge
- **Database:** CockroachDB with [VECTOR / pgvector-compatible](https://www.cockroachlabs.com/docs/stable/vector) search
- **AI:** Amazon Bedrock — Claude 3 (topic extraction), Titan Embed Text v1 (1536-d)
- **IaC:** AWS SAM (`template.yaml`)

## Database

Apply the schema against your CockroachDB cluster:

```bash
export DATABASE_URL='postgresql://user:pass@host:26257/studyai?sslmode=verify-full'
cockroach sql --url "$DATABASE_URL" -f schema/001_init.sql
```

Or any PostgreSQL client:

```bash
psql "$DATABASE_URL" -f schema/001_init.sql
```

Tables: `courses`, `syllabus_topics`, `questions`, `answers`  
View: `topic_coverage` — joins questions to topics when L2 distance `< 0.3`

> VECTOR INDEX syntax needs CockroachDB **25.2+**. On 24.2–25.1, remove the `VECTOR INDEX (...)` lines from `schema/001_init.sql`; exact distance search still works.

## Quick start

### 1. Configure

```bash
cp .env.example .env
# Fill DATABASE_URL, Discord tokens, REPORT_CHANNEL_ID, etc.
python3 -m venv .venv && source .venv/bin/activate
make install
```

### 2. Initialize schema + syllabus

```bash
make schema
python tools/ingest_syllabus.py \
  --file samples/syllabus_cs101.txt \
  --guild-id "$DISCORD_GUILD_ID" \
  --course-name "CS 101"
```

Dry-run topic extraction only:

```bash
python tools/ingest_syllabus.py --file samples/syllabus_cs101.txt \
  --guild-id "$DISCORD_GUILD_ID" --course-name "CS 101" --dry-run
```

### 3. Deploy Lambdas

```bash
sam build
sam deploy --guided
```

Pass `DatabaseUrl`, Discord params, and channel IDs when prompted.  
Outputs include:

- **InteractionsUrl** → Discord Developer Portal → Interactions Endpoint URL  
- **IngestionUrl** → set as `INGESTION_URL` for the gateway relay  

Enable Bedrock model access for Titan Embeddings and Claude 3 in the AWS console (region must match).

### 4. Register slash commands

```bash
make register
```

Commands: `/ask`, `/resolved`, `/gap-report`

### 5. Run the gateway relay (passive capture)

```bash
export INGESTION_URL='https://..../Prod/ingestion'
export RESOLUTION_URL='https://..../Prod/interactions'
make gateway
```

Enable **Message Content Intent** for the bot in the Discord Developer Portal.

## Core workflows

### A. Question ingestion

1. Student posts in `#questions` (or uses `/ask`)
2. Relay / command → Ingestion Lambda
3. Heuristic filter drops bot noise / non-questions
4. Bedrock Titan embeds the text
5. Row inserted into `questions` (`status = open`)

### B. Resolution

- Slash: `/resolved message_id:<id>`
- Reaction: ✅ on the question message (via gateway)
- Optional answer text stored in `answers`

### C. Weekly gap report

EventBridge fires the Gap Report Lambda (default: Friday 17:00 UTC). It reads coverage, then posts an embed with:

1. **Untouched topics** — `question_count = 0`
2. **Unresolved areas** — high `open_count`

Manual trigger: `/gap-report`

### D. Syllabus ingestion

`tools/ingest_syllabus.py` uses Claude to extract topics, Titan to embed them, and inserts into `syllabus_topics`.

## Local invoke (SAM)

```bash
sam local invoke IngestionFunction -e events/message_create.json
```

## Project layout

```
schema/001_init.sql       # CockroachDB DDL + topic_coverage view
src/
  shared/                 # db, bedrock, discord, gap logic
  ingestion/handler.py
  resolution/handler.py
  gap_report/handler.py
tools/
  ingest_syllabus.py
  register_commands.py
gateway/relay.py          # Discord gateway → Lambda forwarder
template.yaml             # AWS SAM
samples/syllabus_cs101.txt
```

## Environment variables

See [`.env.example`](.env.example). Important knobs:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | CockroachDB connection string |
| `SIMILARITY_THRESHOLD` | L2 distance cutoff (default `0.3`) |
| `QUESTIONS_CHANNEL_IDS` | Channels to watch (comma-separated) |
| `REPORT_CHANNEL_ID` | Where weekly embeds are posted |
| `BEDROCK_EMBEDDING_MODEL` | Default `amazon.titan-embed-text-v1` (1536-d) |

## Notes

- Discord slash commands and the Interactions Endpoint are fully serverless. Passive message listening needs the small **gateway relay** (or any process that forwards `MESSAGE_CREATE` to `/ingestion`).
- Tune `SIMILARITY_THRESHOLD` after embedding a sample syllabus; Titan L2 distances differ from cosine setups.
- Multi-course: one active `courses` row per guild (latest active). Extend `get_active_course_for_guild` if you need channel→course mapping.
