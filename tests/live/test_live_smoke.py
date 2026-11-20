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
