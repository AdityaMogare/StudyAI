# Setup checklist — get StudyAI APIs live

Complete these before demo day. Do **not** commit real secrets.

## 1. CockroachDB Cloud

- [ ] Create Serverless (or Dedicated) cluster
- [ ] Create database `studyai`
- [ ] Copy SQL connection string → `DATABASE_URL` in `.env`
- [ ] Enable / confirm VECTOR support (24.2+; VECTOR INDEX 25.2+)
- [ ] Connect Cursor MCP ([MCP_SETUP.md](MCP_SETUP.md)) and authenticate
- [ ] Apply schema:

```bash
export DATABASE_URL='postgresql://...'
make schema          # 001_init.sql
make schema-agent    # 002_agent_memory.sql
```

## 2. AWS + Bedrock

- [ ] AWS account + CLI configured (`aws sts get-caller-identity`)
- [ ] Region set (default `us-east-1`) matching Bedrock model access
- [ ] Enable model access: `amazon.titan-embed-text-v1`, Claude 3 Haiku (or your chosen Claude ID)
- [ ] SAM CLI installed (`sam --version`)

## 3. Discord application

- [ ] Create app at https://discord.com/developers/applications
- [ ] Copy **Application ID**, **Public Key**, create **Bot** → token
- [ ] Enable **Message Content Intent**
- [ ] Invite bot to your demo guild (scopes: `bot`, `applications.commands`)
- [ ] Create `#questions` and `#exam-prep` (or `#announcements`) channels
- [ ] Copy guild + channel IDs into `.env`

## 4. Local `.env`

```bash
cp .env.example .env
# fill all values — never commit .env
```

## 5. Deploy + wire Discord

```bash
make install
make schema && make schema-agent
python tools/ingest_syllabus.py --file samples/syllabus_cs101.txt \
  --guild-id "$DISCORD_GUILD_ID" --course-name "CS 101"
sam build && sam deploy --guided
# Set Discord Interactions Endpoint URL to Outputs.InteractionsUrl
make register
export INGESTION_URL=... RESOLUTION_URL=...
make gateway
```

## 6. Smoke test

- [ ] `/ask How does binary search work?` → linked topics reply
- [ ] MCP/SQL: row in `questions` + `question_topic_links` + `agent_actions`
- [ ] `/memory` → TA digest
- [ ] `/gap-report` → embed in report channel
- [ ] ✅ reaction or `/resolved` → status `resolved`
