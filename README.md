# StudyAI

**Classroom Memory Agent** for Discord: passively captures student questions, maps them to syllabus topics with **CockroachDB distributed VECTOR search**, tracks resolution, and acts by generating TA intervention plans from collective blind spots.

Remote: [AdityaMogare/StudyAI](https://github.com/AdityaMogare/StudyAI) · License: [MIT](LICENSE)

Hackathon docs: [docs/HACKATHON.md](docs/HACKATHON.md) · [docs/SETUP_CHECKLIST.md](docs/SETUP_CHECKLIST.md) · [docs/DEVPOST_SUBMISSION.md](docs/DEVPOST_SUBMISSION.md)

## Architecture

![StudyAI architecture](docs/architecture.svg)

```
Discord ──Gateway relay──► API Gateway ──► Ingestion Lambda ──► Bedrock (Titan embed)
                │                                    │
                │                                    ▼
                │                    CockroachDB (VECTOR + agent_actions)
                │                                    ▲
Slash cmds ─────┴──► Interactions Lambda ────────────┤
                                                     │
EventBridge (Fri 5pm UTC) ──► Gap Report Lambda ─────┘
                                     │
                                     ▼
                    Discord #exam-prep embed + TA plan
```

| Component | Trigger | Role |
|-----------|---------|------|
| **Ingestion Lambda** | `POST /ingestion` | Embed question → store → VECTOR-link topics → log `agent_actions` |
| **Resolution Lambda** | `POST /interactions` | `/ask`, `/resolved`, `/gap-report`, `/memory`, ✅ reactions |
| **Gap Report Lambda** | EventBridge cron | Coverage + Bedrock TA recommendations → Discord embed |
| **Syllabus CLI** | Manual | Claude extracts topics → embeddings → `syllabus_topics` |
| **Gateway relay** | Always-on (local/ECS) | Forwards `MESSAGE_CREATE` + reactions |

## Tech stack

- **UX:** Discord (slash commands + passive channel capture)
- **Compute:** AWS Lambda + API Gateway + EventBridge
- **Database:** CockroachDB [VECTOR / distributed indexing](https://www.cockroachlabs.com/docs/stable/vector)
- **AI:** Amazon Bedrock — Claude 3 (extraction + TA plans), Titan Embed Text v1 (1536-d)
- **Agent tooling:** CockroachDB Cloud [Managed MCP](https://cockroachlabs.cloud/mcp) + Agent Skills
- **IaC:** AWS SAM (`template.yaml`)

## Database

```bash
export DATABASE_URL='postgresql://user:pass@host:26257/studyai?sslmode=verify-full'
make schema        # courses, topics, questions, answers, topic_coverage
make schema-agent  # question_topic_links, agent_actions
```

Tables: `courses`, `syllabus_topics`, `questions`, `answers`, `question_topic_links`, `agent_actions`  
View: `topic_coverage` — semantic join when L2 distance `< 0.3`

> VECTOR INDEX needs CockroachDB **25.2+**. On 24.2–25.1, remove `VECTOR INDEX (...)` lines from `schema/001_init.sql`.

## Quick start

Follow [docs/SETUP_CHECKLIST.md](docs/SETUP_CHECKLIST.md) for Discord / AWS / CockroachDB credentials.

```bash
cp .env.example .env   # fill secrets — never commit .env
python3 -m venv .venv && source .venv/bin/activate
make install
make schema && make schema-agent
python tools/ingest_syllabus.py \
  --file samples/syllabus_cs101.txt \
  --guild-id "$DISCORD_GUILD_ID" \
  --course-name "CS 101"
sam build && sam deploy --guided
# Set Discord Interactions Endpoint URL → Outputs.InteractionsUrl
make register
export INGESTION_URL=... RESOLUTION_URL=...
make gateway
# optional repeatable demo data:
make seed
```

Slash commands: `/ask`, `/resolved`, `/gap-report`, `/memory`

## Core workflows

### A. Question ingestion (memory write + link)

1. Student posts in `#questions` or uses `/ask`
2. Titan embeds the text → `questions` row
3. VECTOR nearest-neighbor links syllabus topics → `question_topic_links`
4. Action logged in `agent_actions` (`topic_link`)

### B. Resolution

- `/resolved`, ✅ reaction, or resolve button
- Updates `questions.status` and optionally `answers`
- Logs `agent_actions` (`resolve`)

### C. Act on memory

- `/memory` — Bedrock reads coverage + recent questions → TA digest (persisted)
- `/gap-report` or Friday cron — Discord embed with untouched topics, open clusters, and agent TA plan

### D. Syllabus ingestion

`tools/ingest_syllabus.py` extracts topics with Claude, embeds with Titan, writes `syllabus_topics`.

## Security & operations

- **Secrets:** store `DATABASE_URL` and Discord tokens in SAM parameters / env — rotate bot tokens if leaked; never commit `.env`
- **Discord:** Interactions Endpoint verified with Ed25519 (`DISCORD_PUBLIC_KEY`)
- **IAM:** Lambda role limited to `bedrock:InvokeModel` (tighten resource ARNs for production)
- **Observability:** CloudWatch logs from each Lambda; query `agent_actions` for an audit trail
- **Resilience:** idempotent `message_id` upserts; gap-report still posts coverage if Bedrock recommendation fails

## Project layout

```
LICENSE
schema/001_init.sql
schema/002_agent_memory.sql
src/shared/           # db, bedrock, agent, discord, gap logic
src/ingestion/
src/resolution/
src/gap_report/
tools/                # syllabus ingest, register commands, seed demo
gateway/relay.py
docs/                 # hackathon, MCP, video script, Devpost draft
template.yaml
```

## Environment variables

See [`.env.example`](.env.example).

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | CockroachDB connection string |
| `SIMILARITY_THRESHOLD` | L2 distance cutoff (default `0.3`) |
| `QUESTIONS_CHANNEL_IDS` | Channels to watch |
| `REPORT_CHANNEL_ID` | Gap-report destination |
| `BEDROCK_EMBEDDING_MODEL` | Default `amazon.titan-embed-text-v1` |
