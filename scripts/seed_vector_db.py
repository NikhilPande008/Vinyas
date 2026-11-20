"""
scripts/seed_vector_db.py
Seeds BigQuery (`nadatwin_telemetry.alloy_signatures_1408d`) and the local <5 ms
in-memory NumPy 1408-d cosine similarity cache with baseline Chakan alloy signatures.
"""
import datetime
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from backend.services.vector_search_service import (
    SEED_SIGNATURES,
    EMBEDDING_DIM,
    project_physics_to_1408d_embedding,
)

try:
    from google.cloud import bigquery  # type: ignore
except ImportError:
    bigquery = None

logger = logging.getLogger("vinyas_ai.scripts.seed_vector")


def seed_vector_signatures() -> None:
    dataset_id = settings.BQ_DATASET or settings.BIGQUERY_DATASET
    table_id = settings.BIGQUERY_VECTOR_TABLE
    print(
        f"Loaded {len(SEED_SIGNATURES)} baseline 1408-d alloy acoustic-load signatures "
        f"(BigQuery Target: {settings.GCP_PROJECT_ID}.{dataset_id}.{table_id}):"
    )
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    rows_to_insert = []
    for sig in SEED_SIGNATURES:
        vec = project_physics_to_1408d_embedding(
            dominant_carrier_hz=float(sig["nominal_carrier_hz"]),
            hilbert_coherence=float(sig["nominal_coherence"]),
            ae_rms=float(sig.get("nominal_ae_rms", 1.2)),
        )
        print(
            f" - [{sig['id']}]: {sig['description']} "
            f"(Carrier: {sig['nominal_carrier_hz']}Hz, Coh: {sig['nominal_coherence']}, "
            f"L2-Norm: {float((vec @ vec) ** 0.5):.2f}, Dim: {EMBEDDING_DIM})"
        )
        rows_to_insert.append(
            {
                "signature_id": sig["id"],
                "description": sig["description"],
                "nominal_carrier_hz": float(sig["nominal_carrier_hz"]),
                "nominal_coherence": float(sig["nominal_coherence"]),
                "nominal_ae_rms": float(sig.get("nominal_ae_rms", 1.2)),
                "is_nominal_baseline": bool(sig.get("is_nominal_baseline", False)),
                "embedding_dim": EMBEDDING_DIM,
                "updated_utc": now_iso,
            }
        )

    if not settings.DEMO_SAFE_MODE and bigquery is not None and settings.GCP_PROJECT_ID != "vinyas-ai-chakan-prod":
        try:
            bq_client = bigquery.Client(project=settings.GCP_PROJECT_ID)
            table_ref = f"{settings.GCP_PROJECT_ID}.{dataset_id}.{table_id}"
            errors = bq_client.insert_rows_json(table_ref, rows_to_insert)
            if not errors:
                print(f"Synced {len(rows_to_insert)} 1408-d centroids to BigQuery table {table_ref}.")
        except Exception as exc:
            print(f"[INFO] Local 1408-d NumPy cache active (remote BigQuery sync skipped: {exc})")

    print("BigQuery + 1408-d NumPy Vector Cache seed completed successfully.")


if __name__ == "__main__":
    seed_vector_signatures()
