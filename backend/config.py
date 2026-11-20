"""Vinyas — Strict Pydantic Configuration Settings (`backend/config.py`).

Reads all configuration from environment variables or `.env` with zero hardcoded keys.
"""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVAL_TOKEN = "vinyas-eval-local"


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
    eval_token: str = Field(default=DEFAULT_EVAL_TOKEN, validation_alias="VINYAS_EVAL_TOKEN")

    # Local SQLite demo store path (resets when Cloud Run container restarts)
    sqlite_db_path: str = Field(
        default=str(PROJECT_ROOT / "vinyas_local.db"),
        validation_alias="SQLITE_DB_PATH",
    )

    # Verified Google AI model routing configuration (see eval/model_selection.md)
    # Tier-1B hedge order chosen by eval/visual_gate_benchmark.md (decision rule fixed before the run)
    tier1_visual_gate_model: str = "gemini-3.5-flash-lite"
    tier1_fallback_model: str = "gemma-4-26b-a4b-it"
    tier1_second_fallback_model: str = "gemini-3.1-flash-lite"
    tier1_hedge_delay_sec: float = 3.0
    tier1_total_timeout_sec: float = 12.0
    tier2_primary_model: str = "gemini-3.1-flash-lite"
    tier2_fallback_model: str = "gemini-3.5-flash-lite"  # eval/model_selection.md run 2; 3.8-flash had no quota
    tier2_hedge_delay_sec: float = 5.7
    tier4_live_copilot_model: str = "gemini-3.8-live"
    tier4_fallback_model: str = "gemini-3.1-flash-lite"
    tier4_second_fallback_model: str = "gemini-3.5-flash-lite"
    embedding_model: str = "gemini-embedding-2"
    embedding_dim: int = 768
    wo_extract_model: str = "gemini-3.1-flash-lite"

    @property
    def t1b_candidates(self) -> list[str]:
        """Tier-1B visual-gate models in hedge order (primary first), without blanks or repeats."""
        out: list[str] = []
        for m in (self.tier1_visual_gate_model, self.tier1_fallback_model, self.tier1_second_fallback_model):
            if m and m not in out:
                out.append(m)
        return out

    @property
    def eval_reveal_enabled(self) -> bool:
        """The eval-token reveal shortcut is off on Cloud Run unless a non-default token is configured.

        The default token is public (it is in this repo), so on a deployed service it would let
        anyone read ground truth before inspecting. Locally it stays on for the eval harness.
        """
        on_cloud_run = bool(os.environ.get("K_SERVICE"))
        return not (on_cloud_run and self.eval_token == DEFAULT_EVAL_TOKEN)

    @property
    def resolved_project_id(self) -> str:
        return self.google_cloud_project or self.gcp_project_id or "vinyas-buildathon-6626"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
