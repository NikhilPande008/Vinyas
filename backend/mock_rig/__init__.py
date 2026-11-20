"""Vinyas Mock Rig v2 — Physics-based simulated sensor & optical inputs (organiser-approved).

Ground-truth labels live ONLY in `data/mock_rig/manifest.json`, which the inference
path never reads.
"""

from backend.mock_rig.dataset import (
    LINE_DEFINITIONS,
    MOCK_RIG_DIR,
    SAMPLES_DIR,
    build_dataset,
    ensure_dataset,
    list_sample_ids_for_line,
    load_sample_public,
)

__all__ = [
    "LINE_DEFINITIONS",
    "MOCK_RIG_DIR",
    "SAMPLES_DIR",
    "build_dataset",
    "ensure_dataset",
    "list_sample_ids_for_line",
    "load_sample_public",
]
