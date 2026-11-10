from datetime import datetime
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # env_ignore_empty: `NOPALIA_FROZEN_NOW=` (empty, as compose passes it) means "unset".
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="NOPALIA_", extra="ignore", env_ignore_empty=True
    )

    database_url: str = "postgresql+psycopg://nopalia:nopalia@localhost:5433/nopalia"
    environment: str = "local"
    log_level: str = "INFO"
    # Business timezone: all "today/tomorrow/cutoff" reasoning happens in Monterrey time.
    timezone: str = "America/Monterrey"
    # Pin the clock (tests, reproducible demos). ISO 8601 with offset.
    frozen_now: datetime | None = None

    # --- secrets: no defaults on purpose; unset means the feature fails closed -----------
    tool_api_token: SecretStr | None = None  # bearer token ElevenLabs tools send
    verification_secret: SecretStr | None = None  # signs caller-verification tokens
    webhook_secret: SecretStr | None = None  # ElevenLabs post-call webhook HMAC secret

    # --- caller verification -------------------------------------------------------------
    verification_ttl_s: int = 1800
    verification_max_failures: int = 3  # per conversation
    verification_store_alert_threshold: int = 10  # per store, across conversations
    verification_window_s: int = 900

    # --- product search ------------------------------------------------------------------
    product_match_threshold: float = 0.35
    # Top two scores closer than this => tell the agent to ask which one.
    product_ambiguity_margin: float = 0.1

    # --- outbound: ticketing system ------------------------------------------------------
    ticketing_url: str = "http://localhost:8081"
    ticketing_max_attempts: int = 3
    ticketing_deadline_s: float = 4.0

    # --- webhooks ------------------------------------------------------------------------
    webhook_tolerance_s: int = 1800  # same window as the official SDK
    webhook_max_future_skew_s: int = 300  # SDK doesn't check the future; we do


@lru_cache
def get_settings() -> Settings:
    return Settings()
