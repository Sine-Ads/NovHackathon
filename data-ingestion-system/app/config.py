"""app/config.py — Application configuration via Pydantic Settings.

All configuration is read from environment variables and .env file.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./haemophilia_data.db"

    # --- Logging ---
    log_level: str = "INFO"

    # --- Retention ---
    data_retention_days: int = 365

    # --- Enabled ingestors ---
    ingestors_enabled: str = (
        "clinical_trials,pubmed,openfda,who_ictrp,medrxiv,arxiv,patents,sec_edgar"
    )

    @property
    def enabled_ingestors_list(self) -> List[str]:
        """Return enabled ingestor names as a list."""
        return [name.strip() for name in self.ingestors_enabled.split(",") if name.strip()]

    # --- Run intervals (minutes) ---
    ingestor_clinical_trials_interval_minutes: int = 1440
    ingestor_pubmed_interval_minutes: int = 1440
    ingestor_openfda_interval_minutes: int = 1440
    ingestor_who_ictrp_interval_minutes: int = 10080
    ingestor_medrxiv_interval_minutes: int = 1440
    ingestor_arxiv_interval_minutes: int = 1440
    ingestor_patents_interval_minutes: int = 10080
    ingestor_sec_edgar_interval_minutes: int = 10080

    def get_interval_minutes(self, ingestor_name: str) -> int:
        """Look up the configured interval for a given ingestor name."""
        attr = f"ingestor_{ingestor_name}_interval_minutes"
        return getattr(self, attr, 1440)

    # --- Rate limiting ---
    api_rate_limit_delay_ms: int = 333
    error_retry_max_attempts: int = 3
    error_retry_base_delay_seconds: float = 2.0

    # --- API Keys ---
    ncbi_api_key: Optional[str] = None
    openfda_api_key: Optional[str] = None
    uspto_api_key: Optional[str] = None

    # --- SEC EDGAR ---
    sec_edgar_user_agent: str = "haemophilia-ingestor admin@example.com"

    # --- Batch limits ---
    ingestor_max_items_per_run: int = 5000

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got '{v}'")
        return upper


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings singleton. Use this everywhere."""
    return Settings()
