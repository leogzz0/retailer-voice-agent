# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first (cached layer), project code second.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000
# Migrations run on start for local dev. In a real deployment they run as a separate
# release step (see docs/03-runbook.md), never from N replicas at once.
CMD ["sh", "-c", "alembic upgrade head && uvicorn nopalia_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
