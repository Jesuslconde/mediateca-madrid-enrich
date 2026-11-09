from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEDIATECA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    database_url: str = "postgresql+psycopg://mediateca:mediateca@localhost:5432/mediateca"
    meilisearch_url: str = "http://localhost:7700"
    meilisearch_key: str = "masterKey"
    meilisearch_index: str = "ediciones"

    opac_base_url: str = "https://gestiona.comunidad.madrid"
    opac_path: str = "/biblio_publicas/cgi-bin/abnetopac"
    raw_dir: Path = Path("./data/raw")
    crawl_delay: float = 1.0
    crawl_timeout: float = 30.0
    crawl_max_retries: int = 3
    user_agent: str = (
        "MediatecaMadrid/0.1 (portal alternativo de consulta; "
        "contacto: mediateca@example.org)"
    )

    api_cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"

    harvest_queries: str = "cine,documental,animacion,musica"
    scheduler_enabled: bool = False
    scheduler_harvest_hours: int = 24

    worker_concurrency: int = 1
    worker_poll_seconds: float = 5.0
    worker_heartbeat_seconds: float = 30.0
    worker_heartbeat_file: Path = Path("/tmp/mediateca-worker.heartbeat")

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.api_cors_origins.split(",") if item.strip()]

    @property
    def queries(self) -> list[str]:
        return [item.strip() for item in self.harvest_queries.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
