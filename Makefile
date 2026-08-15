.PHONY: install schema schema-agent build deploy register gateway seed help

help:
	@echo "StudyAI targets:"
	@echo "  make install       - install Python deps (Lambdas + gateway + tools)"
	@echo "  make schema        - apply schema/001_init.sql (requires DATABASE_URL)"
	@echo "  make schema-agent  - apply schema/002_agent_memory.sql"
	@echo "  make build         - sam build"
	@echo "  make deploy        - sam deploy --guided"
	@echo "  make register      - register Discord slash commands"
	@echo "  make gateway       - run Discord gateway relay"
	@echo "  make seed          - seed demo questions (syllabus must exist)"

install:
	python3 -m pip install -r requirements.txt
	python3 -m pip install -r gateway/requirements.txt

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

register:
	python3 tools/register_commands.py

gateway:
	python3 gateway/relay.py

seed:
	python3 tools/seed_demo.py
