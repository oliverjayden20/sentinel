from functools import lru_cache
from pathlib import Path

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sentinel"
    app_version: str = "1.0.0"
    data_file: Path = Path("data/services.json")
    database_file: Path = Path("data/sentinel.db")
    log_file: Path = Path("logs/system.log")
    monitor_interval_seconds: int = Field(default=30, ge=5)
    request_timeout_seconds: float = Field(default=5.0, gt=0)
    alert_cooldown_seconds: int = Field(default=300, ge=0)
    alert_webhook_url: HttpUrl | None = None

    model_config = SettingsConfigDict(env_prefix="SENTINEL_", env_file=".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()
