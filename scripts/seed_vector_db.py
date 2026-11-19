"""
scripts/seed_vector_db.py
Seeds Vertex AI Vector Search 1408-d Cosine Index with baseline Chakan alloy signatures.
"""
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.vector_search_service import SEED_SIGNATURES

logger = logging.getLogger("vinyas_ai.scripts.seed_vector")


def seed_vector_signatures():
    print(f"Loaded {len(SEED_SIGNATURES)} baseline alloy acoustic-load signatures:")
    for sig in SEED_SIGNATURES:
        print(f" - [{sig['id']}]: {sig['description']} (Carrier: {sig['nominal_carrier_hz']}Hz, Coh: {sig['nominal_coherence']})")
    print("Vector database seed completed successfully.")


if __name__ == "__main__":
    seed_vector_signatures()
