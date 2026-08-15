# Security notes (production readiness)

## Secrets

- Never commit `.env`, bot tokens, or database passwords.
- Prefer AWS SAM parameter overrides / SSM Parameter Store for Lambda env.
- Rotate `DISCORD_BOT_TOKEN` if it appears in logs or screenshots.

## Access control

- Discord Interactions are Ed25519-verified (`DISCORD_PUBLIC_KEY`).
- Restrict `QUESTIONS_CHANNEL_IDS` so only designated channels are ingested.
- CockroachDB Cloud: use least-privilege SQL users; enable MCP read-only where possible during demos.

## Failure modes

| Failure | Behavior |
|---------|----------|
| Bedrock unavailable on ingest | Lambda returns 500; Discord can retry `/ask` |
| Bedrock unavailable on gap-report | Coverage embed still posts; recommendation omitted |
| Duplicate Discord message | `ON CONFLICT (message_id)` upsert |
| No active course | Clear error asking to run syllabus ingest |

## Observability

- CloudWatch Logs for each Lambda function
- `agent_actions` table as application-level audit of memory writes and TA plans
- MCP / SQL dashboards for `topic_coverage` health
