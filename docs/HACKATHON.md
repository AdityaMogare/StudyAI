# Hackathon tool matrix — StudyAI

**Hackathon:** CockroachDB × AWS — Build with Agentic Memory  
**Project:** StudyAI — Classroom Memory Agent for Discord  
**Repo:** https://github.com/AdityaMogare/StudyAI

## CockroachDB tools used (≥2 required)

| Tool | How StudyAI uses it | Evidence in repo |
|---|---|---|
| **Distributed Vector Indexing** | Stores Titan embeddings on `syllabus_topics` / `questions`; nearest-neighbor topic linking; `topic_coverage` view | [schema/001_init.sql](../schema/001_init.sql), [src/shared/db.py](../src/shared/db.py) `fetch_nearest_topics`, [src/shared/agent.py](../src/shared/agent.py) |
| **Cloud Managed MCP Server** | Schema apply/verify, coverage audits, demo inspection of `agent_actions` | [docs/MCP_SETUP.md](MCP_SETUP.md) |
| **Agent Skills (open source)** | Schema/VECTOR index design and CockroachDB production practices followed while building | This doc + schema comments referencing skills guidance |

Optional / stretch: `ccloud` CLI for cluster bootstrap (document if used during your deploy).

## AWS services used (≥1 required)

| Service | How StudyAI uses it | Evidence |
|---|---|---|
| **Amazon Bedrock** | Titan embeddings; Claude topic extraction + TA recommendations | [src/shared/bedrock.py](../src/shared/bedrock.py) |
| **AWS Lambda** | Ingestion, resolution/interactions, weekly gap-report | [template.yaml](../template.yaml), `src/*/handler.py` |
| **API Gateway** | `/ingestion`, `/interactions` HTTP triggers | [template.yaml](../template.yaml) |
| **EventBridge** | Friday cron for gap report | [template.yaml](../template.yaml) |

## Agentic memory design (judging narrative)

CockroachDB is the **system of record** for classroom memory:

1. **Write memory** — student questions + embeddings land in `questions`
2. **Link memory** — VECTOR search links each question to syllabus topics (`question_topic_links`) and logs `agent_actions`
3. **Act on memory** — Bedrock reads coverage + recent questions, writes TA recommendations back to `agent_actions`, Discord posts the plan

Without CockroachDB VECTOR + transactional tables, the agent cannot map questions or produce durable gap reports.

## Setup checklist (credentials)

See [SETUP_CHECKLIST.md](SETUP_CHECKLIST.md) and [../.env.example](../.env.example).
