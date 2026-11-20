"""
config/settings.py
Pydantic BaseSettings for Vinyas 4-Tier Edge-to-Cloud Architecture.
Centralizes live hardware device bindings (Stereo USB ADC, USB Camera, Serial Relay),
current Google GenAI model IDs, calibration scalars, and DEMO_SAFE_MODE controls.
"""
import os
from pathlib import Path
from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class VinyasAISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Google AI & Cloud Credentials
    GEMINI_API_KEY: str = Field(default="demo-offline-api-key")
    GCP_PROJECT_ID: str = Field(default="vinyas-ai-chakan-prod")
    GCP_LOCATION: str = Field(default="asia-south1")
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = Field(
        default=str(PROJECT_ROOT / "secrets" / "vinyas-sa-key.json")
    )
    GCS_QA_VAULT_BUCKET: Optional[str] = Field(default=None)

    # Demo Circuit Breaker & Hardware Source Selection
    DEMO_SAFE_MODE: bool = Field(default=True)
    CIRCUIT_BREAKER_TIMEOUT_SEC: float = Field(default=8.0)
    HARDWARE_SOURCE: Literal["USB_STEREO_ADC", "WAV_REPLAY"] = Field(default="WAV_REPLAY")
    AUDIO_DEVICE_INDEX: Optional[int] = Field(default=None)
    CAMERA_DEVICE_INDEX: int = Field(default=0)
    RELAY_SERIAL_PORT: Optional[str] = Field(default=None)
    RELAY_OPERATING_MODE: Literal["DAY1_ANDON_ONLY", "DAY30_EXT_FEED_HOLD_CUTOUT"] = Field(
        default="DAY1_ANDON_ONLY"
    )

    # Current Google GenAI Model Manifest
    GEMINI_OMNI_MODEL_ID: str = Field(default="gemini-2.5-flash")
    EDGE_GEMMA_MODEL_ID: str = Field(default="gemma-3n-E4B-it")
    VERNACULAR_GEMMA_MODEL_ID: str = Field(default="gemma-3-4b-it")
    GEMINI_IMAGE_MODEL_ID: str = Field(default="gemini-3-pro-image-preview")
    GEMINI_LIVE_MODEL_ID: str = Field(default="gemini-2.0-flash-live-001")
    LYRIA_MODEL_ID: str = Field(default="lyria-002")
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434")

    # Stereo 48 kHz Hardware Sensor Calibration Constants
    SAMPLE_RATE_HZ: int = Field(default=48000)
    WINDOW_DURATION_MS: int = Field(default=250)
    DECIMATION_FACTOR: int = Field(default=24)
    VIBRATION_G_PER_FS: float = Field(default=10.0)
    AE_G_PER_FS: float = Field(default=10.0)
    CT_AMPS_PER_FS: float = Field(default=15.0)
    MAX_AE_RMS_G: float = Field(default=4.5)
    COHERENCE_CHATTER_THRESHOLD: float = Field(default=0.72)
    MIN_CT_RIPPLE_AMPS: float = Field(default=0.12)
    EDGE_SIMILARITY_FAST_PATH_THRESHOLD: float = Field(default=0.88)

    # Provenance & Cloud KMS (EC_SIGN_P256_SHA256)
    HMAC_SIGNING_SECRET: str = Field(default="vinyas-ai-v21-chakan-iatf16949-hmac-key-2026")
    KMS_KEY_RING: str = Field(default="vinyas-qa-keyring")
    KMS_CRYPTO_KEY: str = Field(default="vinyas-cert-signer")
    CLOUD_KMS_KEY_RESOURCE: str = Field(
        default="projects/vinyas-ai-chakan-prod/locations/asia-south1/keyRings/vinyas-qa-keyring/cryptoKeys/vinyas-cert-signer/cryptoKeyVersions/1"
    )

    # BigQuery Vector Search (1408-d Alloy Signatures) & OEE Ledger (nadatwin_telemetry)
    BQ_DATASET: str = Field(default="nadatwin_telemetry")
    BIGQUERY_DATASET: str = Field(default="nadatwin_telemetry")
    BIGQUERY_TABLE: str = Field(default="shift_incidents_ledger")
    BIGQUERY_VECTOR_TABLE: str = Field(default="alloy_signatures_1408d")
    GCS_QA_BUCKET: Optional[str] = Field(default=None)

    # File System Paths
    CONFIG_DIR: Path = Field(default=PROJECT_ROOT / "config")
    DATA_DIR: Path = Field(default=PROJECT_ROOT / "data")
    FALLBACK_CACHE_DIR: Path = Field(default=PROJECT_ROOT / "data" / "fallback_cache")
    GOLDEN_REFS_DIR: Path = Field(default=PROJECT_ROOT / "data" / "golden_references")
    SYNTHETIC_FAULTS_DIR: Path = Field(default=PROJECT_ROOT / "data" / "synthetic_faults")

    # Cloud Run & Local Backend API URL Resolution
    CLOUD_RUN_BACKEND_URL: Optional[str] = Field(default=None)
    BACKEND_API_URL: str = Field(default="http://localhost:8000")

    def resolve_backend_url(self) -> str:
        """Returns CLOUD_RUN_BACKEND_URL when configured, with automatic fallback to BACKEND_API_URL."""
        if self.CLOUD_RUN_BACKEND_URL and self.CLOUD_RUN_BACKEND_URL.strip():
            return self.CLOUD_RUN_BACKEND_URL.strip().rstrip("/")
        return self.BACKEND_API_URL.strip().rstrip("/")

    def load_secret_from_gcp_if_available(self, secret_id: str) -> Optional[str]:
        """
        Optionally resolves runtime secrets (`GEMINI_API_KEY`, `HMAC_SIGNING_SECRET`)
        from Google Cloud Secret Manager when deployed on Cloud Run (`K_SERVICE`).
        """
        if not os.environ.get("K_SERVICE"):
            return None
        try:
            from google.cloud import secretmanager  # type: ignore

            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{self.GCP_PROJECT_ID}/secrets/{secret_id}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("utf-8").strip()
        except Exception:
            return None


settings = VinyasAISettings()

if settings.GOOGLE_APPLICATION_CREDENTIALS:
    _cred_path = Path(settings.GOOGLE_APPLICATION_CREDENTIALS)
    if not _cred_path.is_absolute():
        _cred_path = (PROJECT_ROOT / _cred_path).resolve()
    if _cred_path.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(_cred_path)
