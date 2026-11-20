"""OpsSense AI — Strict Pydantic Configuration Settings (`backend/config.py`).

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
    alloydb_dsn: str = Field(default="", validation_alias="ALLOYDB_DSN")
    gcs_bucket: str = Field(default="", validation_alias="GCS_BUCKET")
    demo_fallback_enabled: bool = Field(
        default=True,
        validation_alias="DEMO_FALLBACK_ENABLED",
    )

    # Local SQLite fallback path for resilient zero-crash execution
    sqlite_fallback_path: str = Field(
        default=str(PROJECT_ROOT / "opssense_local.db"),
        validation_alias="SQLITE_FALLBACK_PATH",
    )

    # Exact Multi-Tier Google AI Model Identifiers
    tier1_edge_physical_model: str = "gemma4:e4b"
    tier1_cloud_emulator_model: str = "gemini-3.5-flash-lite"
    tier2_primary_model: str = "gemini-4-hydrogen"
    tier2_fallback_model: str = "gemini-3.8-flash"
    tier3_visual_sop_model: str = "gemini-nano-banana-2.1"
    tier4_live_copilot_model: str = "gemini-3.8-live"

    # Runtime SDK compatible execution fallback aliases when preview model IDs redirect
    sdk_flash_lite_alias: str = "gemini-2.5-flash-lite"
    sdk_flash_alias: str = "gemini-2.5-flash"
    sdk_image_alias: str = "gemini-2.5-flash-image-preview"

    @property
    def resolved_project_id(self) -> str:
        return self.google_cloud_project or self.gcp_project_id or "vinyas-buildathon-6626"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
