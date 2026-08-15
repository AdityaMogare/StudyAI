# CockroachDB Cloud Managed MCP — StudyAI

StudyAI uses the [CockroachDB Cloud Managed MCP Server](https://cockroachlabs.cloud/mcp) as a second eligibility tool (alongside Distributed Vector Indexing and Agent Skills).

## What the agent / builders use MCP for

- Apply and verify schema (`001_init.sql`, `002_agent_memory.sql`)
- Inspect `topic_coverage` and VECTOR nearest-neighbor results
- Audit `agent_actions` / `question_topic_links` during demos
- Safe-by-default read paths with Cloud audit logging

## Cursor setup

1. Open [CockroachDB Cloud Console](https://cockroachlabs.cloud/) → your cluster → **MCP**.
2. Copy the managed MCP config snippet.
3. Add it to Cursor MCP settings (or use the CockroachDB Cursor plugin).
4. Authenticate when prompted (`mcp_auth`).
5. Confirm tools appear (SQL / cluster introspection).

Endpoint: `https://cockroachlabs.cloud/mcp`

## Example verification queries (run via MCP)

```sql
SHOW TABLES;

SELECT topic_name, question_count, open_count, resolved_count
FROM topic_coverage
ORDER BY open_count DESC, question_count ASC
LIMIT 20;

SELECT action_type, output_summary, created_at
FROM agent_actions
ORDER BY created_at DESC
LIMIT 10;
```

## Agent Skills pairing

Schema and ops guidance for this project follow the open-source [CockroachDB Agent Skills](https://github.com/cockroachdb/agent-skills) patterns (query/schema design, VECTOR indexes, production practices). See [docs/HACKATHON.md](HACKATHON.md).
