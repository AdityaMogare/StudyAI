# Local-first runtime (no AWS Lambda)

Get StudyAI working with CockroachDB + Discord first. Deploy to SAM later by swapping URLs.

## Why

Bedrock quotas and SAM deploy can block a demo. The local FastAPI server runs the **same** Lambda handlers (`ingestion`, `resolution`) over HTTP.

## Prereqs

- Python 3.11+
- CockroachDB `DATABASE_URL` (schema applied)
- Discord bot + guild + channel IDs in `.env`
- Optional: [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/) or [ngrok](https://ngrok.com/) for a public HTTPS URL

## Setup

```bash
cp .env.example .env
# fill DATABASE_URL + Discord fields
# set EMBEDDING_MODE=local

python3 -m venv .venv && source .venv/bin/activate
make install
make schema && make schema-agent
make seed-syllabus
make smoke
```

## Run Discord against local server

**Terminal 1 — API:**

```bash
set -a && source .env && set +a
export EMBEDDING_MODE=local
make local
# listens on http://127.0.0.1:8080
```

**Terminal 2 — public tunnel (for Discord slash commands):**

```bash
cloudflared tunnel --url http://127.0.0.1:8080
# or: ngrok http 8080
```

Copy the `https://…` URL → Discord Developer Portal → **Interactions Endpoint URL**  
→ `https://<tunnel>/interactions`

**Terminal 3 — register + gateway:**

```bash
set -a && source .env && set +a
export INGESTION_URL=http://127.0.0.1:8080/ingestion
export RESOLUTION_URL=http://127.0.0.1:8080/interactions
make register
make gateway
```

## Demo commands

- `/ask How does binary search work?`
- `/memory`
- `/gap-report` (or `make gap-report` from CLI)
- ✅ reaction or `/resolved`

## Switch to AWS later

1. `sam build && sam deploy --guided`
2. Set Discord Interactions URL to SAM `InteractionsUrl`
3. Point gateway at SAM `IngestionUrl` / interactions URL
4. Set `EMBEDDING_MODE=auto` or `bedrock` when Titan quota works

No handler rewrite required — only URLs and env.
