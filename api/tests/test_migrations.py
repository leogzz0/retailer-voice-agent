"""Guards against the classic drift bug: models changed, migration forgotten."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.engine import Engine

from nopalia_api.models import Base


def test_models_match_migrations(engine: Engine) -> None:
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"Models and migrations differ; run `make revision`. Diff: {diff}"
