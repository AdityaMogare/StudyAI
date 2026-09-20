.PHONY: install schema schema-agent build deploy register gateway seed seed-syllabus smoke local gap-report help

help:
	@echo "StudyAI targets:"
	@echo "  make install        - install Python deps (Lambdas + gateway + local server)"
	@echo "  make schema         - apply schema/001_init.sql (requires DATABASE_URL)"
	@echo "  make schema-agent   - apply schema/002_agent_memory.sql"
	@echo "  make build          - sam build"
	@echo "  make deploy         - sam deploy --guided"
	@echo "  make deploy-auto    - non-interactive deploy from .env"
	@echo "  make register       - register Discord slash commands"
	@echo "  make gateway        - run Discord gateway relay"
	@echo "  make seed-syllabus  - offline CS 101 topic seed (no Bedrock chat)"
	@echo "  make seed           - seed demo questions (syllabus must exist)"
	@echo "  make smoke          - local ask/link/memory/resolve smoke test"
	@echo "  make local          - FastAPI local runtime (no AWS Lambda)"
	@echo "  make gap-report     - post gap report to Discord (no EventBridge)"

install:
	python3 -m pip install -r requirements.txt
	python3 -m pip install -r gateway/requirements.txt
	python3 -m pip install -r local_server/requirements.txt

schema:
	@test -n "$$DATABASE_URL" || (echo "DATABASE_URL required" && exit 1)
	@if command -v cockroach >/dev/null 2>&1; then \
		cockroach sql --url "$$DATABASE_URL" -f schema/001_init.sql; \
	else \
		psql "$$DATABASE_URL" -f schema/001_init.sql; \
	fi

schema-agent:
	@test -n "$$DATABASE_URL" || (echo "DATABASE_URL required" && exit 1)
	@if command -v cockroach >/dev/null 2>&1; then \
		cockroach sql --url "$$DATABASE_URL" -f schema/002_agent_memory.sql; \
	else \
		psql "$$DATABASE_URL" -f schema/002_agent_memory.sql; \
	fi

build:
	sam build

deploy:
	sam deploy --guided

deploy-auto:
	bash tools/sam_deploy.sh

register:
	python3 tools/register_commands.py

gateway:
	python3 gateway/relay.py

seed-syllabus:
	python3 tools/seed_syllabus_offline.py --guild-id "$$DISCORD_GUILD_ID" --course-name "CS 101" --replace

seed:
	python3 tools/seed_demo.py

smoke:
	python3 tools/smoke_test_local.py

local:
	python3 local_server/app.py

gap-report:
	python3 tools/run_gap_report.py
