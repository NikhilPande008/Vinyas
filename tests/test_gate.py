"""Phase 3 Tier-1 DSP + Gemma gate unit tests (fast & offline)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from backend.dsp.envelope import analyze_cnc_vibration_envelope, evaluate_t1a_signal_gate
from backend.mock_rig.dataset import MANIFEST_PATH, SAMPLES_DIR, ensure_dataset, load_sample_public
from backend.mock_rig.vibration import FS_HZ, generate_cnc_vibration
from backend.schemas import SensorTelemetry, StageProvenance
from backend.services.gate import combine_tier1_votes


def _ok_t1b_prov() -> StageProvenance:
    return StageProvenance(
        stage="T1B_GATE",
        producer="MODEL",
        model_id="gemma-4-26b-a4b-it",
        latency_ms=120,
        input_simulated=True,
    )


def test_cnc_outer_race_fault_triggers_bpfo_flag_and_escalates():
    rng = np.random.default_rng(101)
    vib = generate_cnc_vibration("OUTER_RACE_FAULT", "severe", rng)
    features, escalating, info, png_bytes = analyze_cnc_vibration_envelope(
        signal=vib.signal_float32,
        fs=FS_HZ,
        rpm=vib.rpm,
        rms_velocity_mms=vib.rms_velocity_mms,
    )
    assert "BEARING_PERIODIC_IMPACT" in escalating
    assert features["bpfo_snr_db"] >= 14.0
    assert features["bpfo_2x_snr_db"] >= 11.0
    assert len(png_bytes) > 500


def test_cnc_wrench_strike_rejected_as_transient_info_only():
    rng = np.random.default_rng(202)
    vib = generate_cnc_vibration("WRENCH_STRIKE", "none", rng)
    features, escalating, info, _ = analyze_cnc_vibration_envelope(
        signal=vib.signal_float32,
        fs=FS_HZ,
        rpm=vib.rpm,
        rms_velocity_mms=vib.rms_velocity_mms,
    )
    assert "BEARING_PERIODIC_IMPACT" not in escalating
    assert "VIBRATION_ZONE_C_OR_D" not in escalating
    assert "TRANSIENT_IMPACT" in info
    assert features["bandpass_kurtosis"] >= 8.0

    # Combined with NOMINAL visual vote -> HEALTHY
    from backend.dsp.envelope import T1AResult

    t1a = T1AResult(line="CNC", escalating_flags=escalating, info_flags=info, features=features, latency_ms=5)
    combined = combine_tier1_votes(
        t1a=t1a,
        t1b_vote="NOMINAL",
        t1b_confidence=0.9,
        t1b_observations=["Machined bore looks normal"],
        t1b_bbox_hint=None,
        t1b_provenance=_ok_t1b_prov(),
        input_simulated=True,
    )
    assert combined.pass_status == "HEALTHY"


def test_nominal_sample_with_nominal_t1b_is_healthy():
    ensure_dataset()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    nom_cnc = next(m for m in manifest if m["line"] == "CNC" and m["defect_type"] == "NOMINAL")
    sample = load_sample_public(nom_cnc["sample_id"])
    t1a = evaluate_t1a_signal_gate(
        line="CNC",
        telemetry=SensorTelemetry(**sample["telemetry"]),
        wav_path=Path(sample["wav_path"]),
    )
    assert not t1a.any_escalating_flag
    combined = combine_tier1_votes(
        t1a=t1a,
        t1b_vote="NOMINAL",
        t1b_confidence=0.92,
        t1b_observations=["Surface nominal"],
        t1b_bbox_hint=None,
        t1b_provenance=_ok_t1b_prov(),
        input_simulated=True,
    )
    assert combined.pass_status == "HEALTHY"


def test_t1b_unavailable_fails_safe_to_escalate():
    from backend.dsp.envelope import T1AResult

    t1a = T1AResult(line="PCB", escalating_flags=[], info_flags=[], features={}, latency_ms=2)
    fail_prov = StageProvenance(
        stage="T1B_GATE",
        producer="FALLBACK_RULES",
        model_id=None,
        latency_ms=4000,
        input_simulated=True,
        note="gate unavailable -> human review",
    )
    combined = combine_tier1_votes(
        t1a=t1a,
        t1b_vote="UNAVAILABLE",
        t1b_confidence=1.0,
        t1b_observations=[],
        t1b_bbox_hint=None,
        t1b_provenance=fail_prov,
        input_simulated=True,
    )
    assert combined.pass_status == "ESCALATE"
    assert "fail-safe" in combined.escalation_reason.lower()
