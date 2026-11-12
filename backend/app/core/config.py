"""Environment-based configuration. No secrets are ever logged or returned by the API."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/versionproof"
    test_database_url: str | None = None
    # Only files under this directory may be ingested through the local ingestion API.
    ingestion_root: Path = Field(default=Path("../data"))
    # Optional providers. "none" keeps the app fully functional without credentials.
    embedding_provider: str = "none"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimensions: int = 384
    llm_provider: str = "none"
    llm_api_key: str | None = None
    # Hard limits for document processing (resource exhaustion guard).
    max_document_bytes: int = 2_000_000
    max_documents_per_job: int = 500
    default_top_k: int = 10

    @property
    def resolved_ingestion_root(self) -> Path:
        return self.ingestion_root.resolve()


settings = Settings()
