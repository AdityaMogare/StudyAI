.PHONY: install schema build deploy register gateway help

help:
	@echo "StudyAI targets:"
	@echo "  make install   - install Python deps (Lambdas + gateway + tools)"
	@echo "  make schema    - apply schema/001_init.sql (requires DATABASE_URL)"
	@echo "  make build     - sam build"
	@echo "  make deploy    - sam deploy --guided"
	@echo "  make register  - register Discord slash commands"
	@echo "  make gateway   - run Discord gateway relay"

install:
	python3 -m pip install -r requirements.txt
	python3 -m pip install -r gateway/requirements.txt

schema:
	@test -n "$$DATABASE_URL" || (echo "DATABASE_URL required" && exit 1)
	cockroach sql --url "$$DATABASE_URL" -f schema/001_init.sql

build:
	sam build

deploy:
	sam deploy --guided

register:
	python3 tools/register_commands.py

gateway:
	python3 gateway/relay.py
