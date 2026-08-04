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

    @property
    def alpaca_headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.alpaca_api_key,
            "APCA-API-SECRET-KEY": self.alpaca_secret_key,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
