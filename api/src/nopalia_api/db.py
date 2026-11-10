from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from nopalia_api.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    get_engine()
    assert _session_factory is not None
    with _session_factory() as session:
        yield session
