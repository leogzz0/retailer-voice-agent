.DEFAULT_GOAL := help
API := cd api &&

.PHONY: help up down reset logs seed test lint fmt typecheck check revision

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Build and start Postgres + API (http://localhost:8000/docs)
	docker compose up -d --build --wait

down: ## Stop containers (keeps data)
	docker compose down

reset: ## Stop containers AND delete the database volume
	docker compose down -v

logs: ## Tail API logs
	docker compose logs -f api

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
