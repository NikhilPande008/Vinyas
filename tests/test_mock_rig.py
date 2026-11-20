"""Phase 2 Mock Rig v2 tests: zero text, manifest isolation, blind draw & reveal gating."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.config import PROJECT_ROOT
from backend.main import _inspected_samples, app, model_router, rate_limiter
from backend.mock_rig.dataset import MANIFEST_PATH, ensure_dataset
from backend.mock_rig.vibration import compute_bearing_frequencies


def test_dataset_composition_and_bpfo_math():
    ensure_dataset()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert len(manifest) == 60
    for line in ("PCB", "CNC", "WELD"):
        subset = [m for m in manifest if m["line"] == line]
        assert len(subset) == 20
        defects = [m for m in subset if m["is_defect"]]
        assert len(defects) == 7

    freqs = compute_bearing_frequencies(rpm=5400)
    assert 785.0 <= freqs["bpfo_hz"] <= 800.0
    assert 1000.0 <= freqs["bpfi_hz"] <= 1015.0


def test_mock_rig_images_have_no_text_calls():
    src = (PROJECT_ROOT / "backend" / "mock_rig" / "images.py").read_text(encoding="utf-8")
    assert ".text(" not in src
    assert "textbbox(" not in src
    assert "SynthID" not in src


def test_inference_services_never_reference_manifest():
    services_dir = PROJECT_ROOT / "backend" / "services"
    for py_file in services_dir.glob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        assert "mock_rig/manifest.json" not in text, f"{py_file} must never read mock_rig/manifest.json"
        assert "MANIFEST_PATH" not in text, f"{py_file} must never read MANIFEST_PATH"


def test_draw_and_reveal_gating():
    rate_limiter.reset()
    _inspected_samples.clear()
    client = TestClient(app)

    draw = client.post("/api/rig/draw", json={"line": "CNC"})
    assert draw.status_code == 200
    payload = draw.json()
    sid = payload["sample_id"]
    assert sid.startswith("CNC-")
    assert "label" not in payload
    assert "defect_type" not in payload
    assert "is_defect" not in payload
    assert payload["input_simulated"] is True

    # Reveal before inspection -> 403
    rev_before = client.get(f"/api/rig/reveal/{sid}")
    assert rev_before.status_code == 403

    # Inspect with mocked model -> reveal unlocks
    orig_client = model_router._client
    model_router.set_client(
        SimpleNamespace(
            models=SimpleNamespace(
                generate_content=lambda model, contents, config=None: SimpleNamespace(
                    text=json.dumps({"vote": "NOMINAL", "confidence": 0.9, "reason": "ok"}),
                    usage_metadata=SimpleNamespace(prompt_token_count=50, candidates_token_count=10),
                )
            )
        )
    )
    try:
        insp = client.post("/api/inspect", json={"sample_id": sid})
        assert insp.status_code == 200
        rev_after = client.get(f"/api/rig/reveal/{sid}")
        assert rev_after.status_code == 200
        assert rev_after.json()["sample_id"] == sid
        assert rev_after.json()["label"] in ("DEFECT", "NOMINAL")
    finally:
        model_router.set_client(orig_client)
