from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NOPALIA_", extra="ignore")

    database_url: str = "postgresql+psycopg://nopalia:nopalia@localhost:5433/nopalia"
    environment: str = "local"
    # Business timezone: all "today/tomorrow" reasoning happens in Monterrey time.
    timezone: str = "America/Monterrey"


@lru_cache
def get_settings() -> Settings:
    return Settings()
