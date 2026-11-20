"""Live smoke tests (skipped unless RUN_LIVE=1)."""

from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from backend.main import app, rate_limiter


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="Set RUN_LIVE=1 to run live smoke tests"),
]


def test_live_draw_inspect_reveal_and_copilot():
    rate_limiter.reset()
    client = TestClient(app)

    draw = client.post("/api/rig/draw", json={"line": "CNC"})
    assert draw.status_code == 200
    sid = draw.json()["sample_id"]

    insp = client.post("/api/inspect", json={"sample_id": sid})
    assert insp.status_code == 200
    body = insp.json()
    assert body["tier1_triage"]["pass_status"] in ("HEALTHY", "ESCALATE")
    assert len(body["provenance"]) >= 2

    rev = client.get(f"/api/rig/reveal/{sid}")
    assert rev.status_code == 200
    assert rev.json()["sample_id"] == sid

    chat = client.post(
        "/api/copilot/chat",
        json={"question": "What is the bearing locknut torque spec?", "line": "CNC", "language": "en-IN"},
    )
    assert chat.status_code == 200
    assert chat.json()["answer"]


def test_live_t1b_primary_model_answers():
    """Fail unless the configured T1-B primary model answers a live PCB visual-gate call."""
    from backend.config import get_settings

    rate_limiter.reset()
    client = TestClient(app)
    primary = get_settings().tier1_visual_gate_model

    draw = client.post("/api/rig/draw", json={"line": "PCB"})
    assert draw.status_code == 200
    sid = draw.json()["sample_id"]

    insp = client.post("/api/inspect", json={"sample_id": sid})
    assert insp.status_code == 200
    t1b = insp.json()["tier1_triage"]["provenance_t1b"]
    primary_attempts = [a for a in t1b.get("attempts", []) if a["model_id"] == primary]
    assert primary_attempts, f"Primary model {primary} was never attempted: {t1b}"
    assert primary_attempts[0]["status"] == "OK", (
        f"Primary T1-B model {primary} did not answer OK: {primary_attempts[0]}"
    )
