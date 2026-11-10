"""Tests run against a real Postgres (pg_trgm/unaccent/JSONB can't be faked with SQLite).

Locally: `make test` (uses the compose db, database `nopalia_test`).
CI: a postgres service container; URL passed via NOPALIA_TEST_DATABASE_URL.
The clock is frozen at Monday 2026-11-09 10:00 Monterrey time.
"""

import os
from collections.abc import Callable, Iterator
from pathlib import Path

TEST_DB_URL = os.environ.get(
    "NOPALIA_TEST_DATABASE_URL",
    "postgresql+psycopg://nopalia:nopalia@localhost:5433/nopalia_test",
)
# Must happen before the app reads settings.
os.environ.update(
    {
        "NOPALIA_DATABASE_URL": TEST_DB_URL,
        "NOPALIA_ENVIRONMENT": "test",
        "NOPALIA_FROZEN_NOW": "2026-11-09T10:00:00-06:00",
        "NOPALIA_TOOL_API_TOKEN": "test-tool-token",
        "NOPALIA_VERIFICATION_SECRET": "test-verification-secret",
        "NOPALIA_WEBHOOK_SECRET": "test-webhook-secret",
        "NOPALIA_LOG_LEVEL": "WARNING",
    }
)

import httpx2 as httpx  # noqa: E402
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
from nopalia_api.ticketing import TicketingClient, get_ticketing_client  # noqa: E402

API_DIR = Path(__file__).resolve().parents[1]
CONVERSATION_ID = "conv_test_0001"
BASE_HEADERS = {
    "Authorization": "Bearer test-tool-token",
    "X-Conversation-Id": CONVERSATION_ID,
}
# Demo stores and the last 4 digits of their registered phones.
PHONE_LAST4 = {"10234": "1234", "20518": "2518", "31007": "3107"}


def alembic_config() -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)
    cfg.attributes["configure_logger"] = False
    return cfg


def _seed(eng: Engine) -> None:
    with Session(eng) as db:
        seed(db, random_stores=10)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    get_settings.cache_clear()
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(alembic_config(), "head")
    _seed(eng)
    yield eng


@pytest.fixture
def reseed(engine: Engine) -> Iterator[Engine]:
    """For tests that write: fresh data before, and restored after for the next test."""
    _seed(engine)
    yield engine
    _seed(engine)


class FakeTicketing:
    """Scriptable upstream: queue responses ('ok', 503, 'timeout'); default is 'ok'."""

    def __init__(self) -> None:
        self.script: list[object] = []
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        step = self.script.pop(0) if self.script else "ok"
        if step == "timeout":
            raise httpx.ReadTimeout("simulated", request=request)
        if isinstance(step, int):
            return httpx.Response(step, json={"error": "simulated"})
        return httpx.Response(201, json={"ticket_id": f"ZD-{len(self.requests):05d}"})


@pytest.fixture
def ticketing() -> Iterator[FakeTicketing]:
    fake = FakeTicketing()
    client = TicketingClient(
        httpx.Client(base_url="http://ticketing.test", transport=httpx.MockTransport(fake.handler)),
        max_attempts=3,
        sleep=lambda _: None,
    )
    app.dependency_overrides[get_ticketing_client] = lambda: client
    yield fake
    app.dependency_overrides.pop(get_ticketing_client, None)


@pytest.fixture(scope="session")
def client(engine: Engine) -> Iterator[TestClient]:
    with TestClient(app, headers=BASE_HEADERS) as c:
        yield c


@pytest.fixture(scope="session")
def anon_client(engine: Engine) -> Iterator[TestClient]:
    """No auth headers at all."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def verified(client: TestClient) -> Callable[[str], dict[str, str]]:
    """verified("10234") -> headers carrying a valid verification token for that store."""

    def _verify(code: str) -> dict[str, str]:
        r = client.post(f"/v1/customers/{code}/verify", json={"phone_last4": PHONE_LAST4[code]})
        assert r.status_code == 200, r.text
        return {"X-Verification-Token": r.json()["verification_token"]}

    return _verify
