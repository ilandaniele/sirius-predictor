from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_prefix="SIRIUS_",
        extra="ignore",
    )

    environment: str = "development"
    database_url: str = "sqlite:///./state/sirius.db"
    redis_url: str = "redis://localhost:6379/0"
    storage_path: Path = ROOT / "storage"
    scenario_path: Path = ROOT / "data" / "scenario.yaml"
    scenario_48_path: Path = ROOT / "data" / "scenario-48.yaml"
    teams_path: Path = ROOT / "data" / "teams.csv"
    sources_path: Path = ROOT / "data" / "sources.yaml"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    http_timeout_seconds: float = 15.0
    http_max_bytes: int = 5 * 1024 * 1024
    collector_rate_limit_seconds: float = 1.0
    default_simulations: int = 100_000
    model_version: str = "0.2.1"
    api_key: SecretStr | None = None
    post_rate_limit_per_minute: int = 10

    def scenario_path_for(self, format_size: int = 64) -> Path:
        if format_size == 64:
            return self.scenario_path
        if format_size == 48:
            return self.scenario_48_path
        raise ValueError("format_size must be 48 or 64")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
