from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(alias="DATABASE_URL")
    alpaca_api_key: str = Field(alias="ALPACA_API_KEY")
    alpaca_secret_key: str = Field(alias="ALPACA_SECRET_KEY")
    alpaca_data_base_url: str = Field(default="https://data.alpaca.markets", alias="ALPACA_DATA_BASE_URL")
    alpaca_trading_base_url: str = Field(default="https://paper-api.alpaca.markets", alias="ALPACA_TRADING_BASE_URL")

    app_username: str = Field(default="admin", alias="APP_USERNAME")
    app_password: str = Field(default="change-me", alias="APP_PASSWORD")
    auto_migrate: bool = Field(default=True, alias="AUTO_MIGRATE")

    staging_dir: Path = Field(default=Path("/var/data/staging"), alias="STAGING_DIR")
    worker_poll_seconds: float = Field(default=3.0, alias="WORKER_POLL_SECONDS")
    worker_stale_seconds: int = Field(default=180, alias="WORKER_STALE_SECONDS")
    max_global_concurrency: int = Field(default=12, alias="MAX_GLOBAL_CONCURRENCY")
    default_target_rpm: int = Field(default=9000, alias="DEFAULT_TARGET_RPM")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Database connection demand is not the same thing as job concurrency.  The
    # Supabase Session Pooler has a finite per-user backend budget, and Render may
    # briefly run old and new instances together during a rolling deployment.
    # Keep these independent so three services cannot each reserve a pool sized
    # for every worker coroutine.
    db_pool_min_size: int = Field(default=1, alias="DB_POOL_MIN_SIZE")
    db_pool_max_size: int = Field(default=4, alias="DB_POOL_MAX_SIZE")
    db_pool_timeout_seconds: float = Field(default=30.0, alias="DB_POOL_TIMEOUT_SECONDS")
    db_pool_max_idle_seconds: float = Field(default=120.0, alias="DB_POOL_MAX_IDLE_SECONDS")
    db_pool_max_lifetime_seconds: float = Field(default=900.0, alias="DB_POOL_MAX_LIFETIME_SECONDS")
    db_pool_max_waiting: int = Field(default=64, alias="DB_POOL_MAX_WAITING")
    db_application_name: str = Field(default="alpaca-rapid-discovery", alias="DB_APPLICATION_NAME")

    @property
    def alpaca_headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.alpaca_api_key,
            "APCA-API-SECRET-KEY": self.alpaca_secret_key,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
