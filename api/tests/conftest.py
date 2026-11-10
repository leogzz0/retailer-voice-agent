"""Tests run against a real Postgres (pg_trgm/unaccent can't be faked with SQLite).

Locally: `make test` (uses the compose db, database `nopalia_test`).
CI: a postgres service container; URL passed via NOPALIA_TEST_DATABASE_URL.
"""

import os
from collections.abc import Iterator
from pathlib import Path

TEST_DB_URL = os.environ.get(
    "NOPALIA_TEST_DATABASE_URL",
    "postgresql+psycopg://nopalia:nopalia@localhost:5433/nopalia_test",
)
# Must happen before the app reads settings.
os.environ["NOPALIA_DATABASE_URL"] = TEST_DB_URL
os.environ["NOPALIA_ENVIRONMENT"] = "test"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from nopalia_api.config import get_settings  # noqa: E402
from nopalia_api.db import get_engine  # noqa: E402
from nopalia_api.main import app  # noqa: E402
from nopalia_api.seed import seed  # noqa: E402

API_DIR = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    get_settings.cache_clear()
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(alembic_config(), "head")
    with Session(eng) as db:
        seed(db, random_stores=10)
    yield eng


@pytest.fixture(scope="session")
def client(engine: Engine) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c
