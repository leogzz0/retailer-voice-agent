.DEFAULT_GOAL := help
API := cd api &&

.PHONY: help env up down reset logs seed test lint fmt typecheck check revision retry-handoffs latency tunnel \
	agent-provision agent-render agent-deploy agent-pull \
	agent-tests-validate agent-tests-push agent-tests-run
ELEVEN := cd agent && . $$HOME/.nvm/nvm.sh >/dev/null 2>&1; elevenlabs

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

env: ## Create .env with fresh random local secrets (never overwrites)
	@test -f .env && echo ".env already exists, leaving it alone" || ( \
		cp .env.example .env && \
		for k in NOPALIA_TOOL_API_TOKEN NOPALIA_VERIFICATION_SECRET NOPALIA_WEBHOOK_SECRET; do \
			v=$$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))'); \
			sed -i.bak "s|^$$k=.*|$$k=$$v|" .env; \
		done && rm -f .env.bak && echo "Created .env with random secrets")

up: ## Build and start Postgres, API and ticketing stub (http://localhost:8000/docs)
	docker compose up -d --build --wait

down: ## Stop containers (keeps data)
	docker compose down

reset: ## Stop containers AND delete the database volume
	docker compose down -v

logs: ## Tail API logs (JSON)
	docker compose logs -f --no-log-prefix api

seed: ## Reload fictional demo data (wipes tables)
	docker compose exec api python -m nopalia_api.seed

test: ## Run tests against the compose Postgres (db must be up)
	docker compose up -d --wait db
	$(API) uv run pytest

lint: ## Ruff lint + format check
	$(API) uv run ruff check . && uv run ruff format --check .

fmt: ## Auto-fix lint and formatting
	$(API) uv run ruff check --fix . && uv run ruff format .

typecheck: ## mypy
	$(API) uv run mypy

check: lint typecheck test ## Everything CI runs

revision: ## New Alembic migration from model changes: make revision m="add incidents"
	$(API) NOPALIA_DATABASE_URL=postgresql+psycopg://nopalia:nopalia@localhost:5433/nopalia \
		uv run alembic revision --autogenerate -m "$(m)"

retry-handoffs: ## Re-deliver pending/failed handoffs to the ticketing system (outbox sweep)
	docker compose exec api python -m nopalia_api.ticketing

latency: ## Fire demo traffic at the API, then print p50/p95 per tool from the JSON logs
	uv run --project api python scripts/latency_report.py --generate 30 --env-file .env
	docker compose logs --no-log-prefix api | uv run --project api python scripts/latency_report.py

tunnel: ## Expose the local API at your ngrok static domain (reads agent/.env)
	@set -a; . agent/.env; set +a; ngrok http --url=$$NOPALIA_PUBLIC_HOST 8000

agent-provision: ## Upsert secret, env vars, KB docs and tools in ElevenLabs (agent/provision.py)
	cd agent && uv run python provision.py

agent-render: ## Render agent/agent_configs/vera.json from prompt, IDs and settings
	cd agent && uv run python render_agent.py

agent-deploy: agent-provision agent-render ## Provision, render and push the Vera agent
	$(ELEVEN) agents push --version-description "$$(git rev-parse --short HEAD 2>/dev/null || echo local)"

agent-pull: ## Pull the live agent config (to see dashboard edits), then re-render
	$(ELEVEN) agents pull --update --yes
	$(MAKE) agent-render

agent-tests-validate: ## Validate agent test definitions offline (free)
	cd agent && uv run python agent_tests.py validate

agent-tests-push: ## Create/update the agent tests in ElevenLabs (free, does not run them)
	cd agent && uv run python agent_tests.py push

agent-tests-run: ## Run the low-cost agent tests (USES CREDITS; add ARGS=--include-expensive)
	cd agent && uv run python agent_tests.py run --yes-spend-credits $(ARGS)
