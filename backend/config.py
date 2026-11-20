"""Vinyas — Strict Pydantic Configuration Settings (`backend/config.py`).

Reads all configuration from environment variables or `.env` with zero hardcoded keys.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core Google Cloud & Gemini Credentials (strictly no hardcoded keys)
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    google_cloud_project: str = Field(
        default="",
        validation_alias="GOOGLE_CLOUD_PROJECT",
    )
    gcp_project_id: str = Field(default="", validation_alias="GCP_PROJECT_ID")
    gcp_location: str = Field(default="asia-south1", validation_alias="GCP_LOCATION")
    eval_token: str = Field(default="vinyas-eval-local", validation_alias="VINYAS_EVAL_TOKEN")

    # Local SQLite demo store path (resets when Cloud Run container restarts)
    sqlite_db_path: str = Field(
        default=str(PROJECT_ROOT / "vinyas_local.db"),
        validation_alias="SQLITE_DB_PATH",
    )

    # Verified Google AI model routing configuration (see eval/model_selection.md)
    tier1_visual_gate_model: str = "gemma-4-26b-a4b-it"
    tier1_fallback_model: str = "gemini-3.1-flash-lite"
    tier2_primary_model: str = "gemini-3.5-flash"
    tier2_fallback_model: str = "gemini-3.1-flash-lite"
    tier2_hedge_delay_sec: float = 4.5
    tier4_live_copilot_model: str = "gemini-3.8-live"
    tier4_fallback_model: str = "gemini-3.1-flash-lite"
    embedding_model: str = "gemini-embedding-2"
    embedding_dim: int = 768
    wo_extract_model: str = "gemini-3.1-flash-lite"

    @property
    def resolved_project_id(self) -> str:
        return self.google_cloud_project or self.gcp_project_id or "vinyas-buildathon-6626"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
