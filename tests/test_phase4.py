"""Phase 4 unit tests: SOP guard, deterministic economics, model-bbox overlay, and Live WebSocket."""

from __future__ import annotations

import base64
import io
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image

from backend.config import PROJECT_ROOT
from backend.main import app, model_router, rate_limiter
from backend.schemas import Evidence, Tier2DiagnosisResult
from backend.services.economics import calculate_avoidable_loss
from backend.services.overlay import render_model_bbox_overlay
from backend.services.sop_guard import guard_steps_against_sop


def test_sop_guard_flags_injected_wrong_torque():
    sop_refs = [
        "Torque spindle bearing locknut to 145 Nm and flush air-oil mist at 0.35 MPa.",
        "Verify taper runout < 0.003 mm TIR.",
    ]
    steps = [
        "Torque locknut to 145 Nm and check 0.35 MPa air-oil mist.",
        "Tighten locknut to 260 Nm and heat housing to 190°C.",
    ]
    checked, unverified_count = guard_steps_against_sop(steps, sop_refs)
    assert checked[0].unverified is False
    assert checked[0].unverified_values == []
    assert checked[1].unverified is True
    assert unverified_count == 2
    assert any("260" in v for v in checked[1].unverified_values)
    assert any("190" in v for v in checked[1].unverified_values)


def test_economics_zero_for_nominal_and_deterministic_for_defects():
    assert calculate_avoidable_loss("PCB", "NO_DEFECT_FOUND", "LOW") == {
        "avoidable_loss_inr": 0,
        "downtime_prevented_mins": 0,
    }
    assert calculate_avoidable_loss("CNC", "NOMINAL", "CRITICAL") == {
        "avoidable_loss_inr": 0,
        "downtime_prevented_mins": 0,
    }
    cnc_crit = calculate_avoidable_loss("CNC", "OUTER_RACE_FAULT", "CRITICAL")
    assert cnc_crit["avoidable_loss_inr"] > 0
    assert cnc_crit["downtime_prevented_mins"] == 45


def test_overlay_has_no_hardcoded_boxes_and_draws_none_for_no_defect():
    src = (PROJECT_ROOT / "backend" / "services" / "overlay.py").read_text(encoding="utf-8")
    assert "bbox_by_scenario" not in src
    assert "SynthID" not in src

    # Create a plain dark-gray 500x300 uploaded image (NOT 640x420)
    buf = io.BytesIO()
    Image.new("RGB", (500, 300), (40, 45, 50)).save(buf, format="PNG")
    raw_bytes = buf.getvalue()

    diag_none = Tier2DiagnosisResult(
        incident_id="INC-TEST-1",
        defect_type="NO_DEFECT_FOUND",
        defect_class="No Defect Found",
        severity="LOW",
        confidence=0.9,
        root_cause_analysis="Part looks nominal.",
        evidence=[
            Evidence(source="image", observation="Clean pads"),
            Evidence(source="telemetry", observation="Nominal reflow"),
        ],
        bbox=[100, 100, 300, 300],  # even if present, NO_DEFECT_FOUND must suppress box
        matched_sop_id="SOP-PUNE-PCB-01",
        skill_applied="pcb-defect-triage",
        recommended_disposition="RELEASE",
        repair_steps=["Release part after QE confirmation."],
        safety_precautions=["Follow ESD handling."],
    )
    data_url, prov = render_model_bbox_overlay(
        raw_image_bytes=raw_bytes,
        diagnosis=diag_none,
        torque_spec="4.5 Nm",
        bbox_source_model="gemini-3.5-flash",
        input_simulated=False,
    )
    assert "No defect location returned" in (prov.note or "")
    out_img = Image.open(io.BytesIO(base64.b64decode(data_url.split(",")[1])))
    assert out_img.size == (500, 368)  # preserved 500x300 + 68px strip
    # Check top 300px image area has zero red box pixels (239, 68, 68)
    top_pixels = list(out_img.crop((0, 0, 500, 300)).getdata())
    assert (239, 68, 68) not in top_pixels

    # With a real defect + model bbox -> draws red rectangle
    diag_def = diag_none.model_copy(update={"defect_type": "SOLDER_BRIDGE", "recommended_disposition": "HOLD"})
    data_url2, prov2 = render_model_bbox_overlay(
        raw_image_bytes=raw_bytes,
        diagnosis=diag_def,
        torque_spec="4.5 Nm",
        bbox_source_model="gemini-3.5-flash",
        input_simulated=False,
    )
    assert "bbox located by gemini-3.5-flash" in (prov2.note or "")
    out_img2 = Image.open(io.BytesIO(base64.b64decode(data_url2.split(",")[1])))
    top_pixels2 = list(out_img2.crop((0, 0, 500, 300)).getdata())
    assert (239, 68, 68) in top_pixels2


def test_websocket_live_copilot_path():
    rate_limiter.reset()
    orig_client = model_router._client
    model_router.set_client(None)  # triggers deterministic SOP fallback cleanly offline
    try:
        client = TestClient(app)
        with client.websocket_connect("/api/live-copilot") as ws:
            ws.send_text(json.dumps({"question": "What is the torque spec?", "line": "CNC", "language": "hi-IN"}))
            resp = ws.receive_json()
            assert "answer" in resp
            assert resp["producer"] == "FALLBACK_RULES"
            assert resp["grounded_sop_id"]
    finally:
        model_router.set_client(orig_client)
