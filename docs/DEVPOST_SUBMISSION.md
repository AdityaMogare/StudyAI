# Devpost submission draft — StudyAI

Copy/paste into Devpost. Replace bracketed placeholders after deploy + video upload.

## Project name

StudyAI — Classroom Memory Agent

## Tagline

Agents that remember what the whole class still doesn’t understand — before the exam.

## Description

StudyAI is an agentic classroom memory system on Discord. It passively captures student questions, embeds them with Amazon Bedrock (Titan), stores durable memory in CockroachDB with distributed VECTOR indexes, links each question to syllabus topics, tracks resolution, and acts by generating TA intervention plans from coverage gaps.

CockroachDB is not a side cache: it is the system of record for embeddings, transactional Q&A state, topic links, and agent action history. Without that memory layer, the agent cannot map questions or report collective blind spots.

## Public repo

https://github.com/AdityaMogare/StudyAI

License: MIT (`LICENSE` at repo root)

## Demo app URL

[Discord invite to demo server / bot instructions — paste after creating invite]

Demo path for judges:
1. Join the StudyAI demo Discord
2. `/ask <question>` in `#questions`
3. `/memory` for live TA digest from CockroachDB memory
4. `/gap-report` for weekly embed with Bedrock recommendations

## Demo video URL

[YouTube or Vimeo public link — see docs/VIDEO_SCRIPT.md]

## CockroachDB tools used

1. **Distributed Vector Indexing** — `VECTOR(1536)` + `VECTOR INDEX` on syllabus topics and questions; nearest-neighbor topic linking; `topic_coverage` view for gap reports.
2. **Cloud Managed MCP Server** — schema apply/verify and live inspection of coverage + `agent_actions` during build and demo (`docs/MCP_SETUP.md`).
3. **Agent Skills** — CockroachDB schema/VECTOR and production guidance used while designing the memory model.

## AWS services used

1. **Amazon Bedrock** — Titan embeddings; Claude for syllabus extraction and TA recommendations.
2. **AWS Lambda** — ingestion, Discord interactions, weekly gap-report functions.
3. **API Gateway + EventBridge** — HTTP triggers and Friday cron schedule.

## Architectural diagram

See `docs/architecture.svg` in the repository.

## Optional feedback on CockroachDB AI tools

[Add 2–3 sentences after using MCP + VECTOR in practice.]
