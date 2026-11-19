"""
tests/test_ppap_sandbox.py
Unit tests verifying:
1. Legacy PPAP sandbox verifier (`verify_ppap_window`)
2. Deterministic Physics Control-Plan Solver (`control_plan_solver.py`):
   - Clamps Feedrate Dial [70..110]%, Spindle Speed Dial [80..115]%, Relative Chip-Load [0.65..1.15]
   - Emits [PASS] assertion badges
3. Economic ROI & validated 1.6-month (~48 days) net hardware payback math
4. Cryptographic Pillow QA / Foundry Chargeback Certificate signing & verification (`KMSCertificateService`)
"""
import json
from pathlib import Path
import pytest
from backend.models.schemas import (
    PPAPRemediationPlan,
    Day1NonInvasiveAction,
    Tier2AutomatedFocasPayload,
    AOIInspectionResult,
    InCycleTelemetrySummary,
)
from backend.skills.ppap_sandbox_verifier import verify_ppap_window
from backend.skills.control_plan_solver import solve_deterministic_control_plan
from backend.skills.roi_calculator import calculate_remediation_roi, calculate_hardware_payback
from backend.services.kms_certificate_service import KMSCertificateService

LIMITS_PATH = Path("config/ppap_control_limits.json")
CONTROL_PLAN_PATH = Path("config/control_plan_limits.json")


@pytest.fixture
def control_limits():
    return json.loads(LIMITS_PATH.read_text())


@pytest.fixture
def control_plan_limits():
    return json.loads(CONTROL_PLAN_PATH.read_text())


@pytest.fixture
def base_valid_plan():
    return PPAPRemediationPlan(
        defect_classification="Carbide Insert Flank Wear",
        detected_harmonic_hz=4210.0,
        envelope_coherence_score=0.84,
        is_false_positive=False,
        target_tool_id="T03",
        day1_manual_action=Day1NonInvasiveAction(
            operator_feedrate_dial_pct=85,
            m01_manual_wear_offset_z_microns=12.0,
            require_insert_indexing=True,
            operator_card_marathi="Feedrate 85% kara ani insert badla.",
        ),
        tier2_focas_simulation=Tier2AutomatedFocasPayload(
            focas_target_register="G10_L11_P03",
            programmed_rpm_override=3400,
        ),
        cycle_time_penalty_sec=4.2,
        estimated_savings_inr=16200,
        implementation_plan_md="# Plan",
        todo_checklist_md="- [x] Check",
    )


def test_ppap_sandbox_valid_plan_passes_all_badges(control_limits, base_valid_plan):
    all_passed, badges = verify_ppap_window(base_valid_plan, control_limits)
    assert all_passed is True
    assert len(badges) == 4
    assert all(b["passed"] for b in badges)


def test_ppap_sandbox_blocks_excessive_feedrate(control_limits, base_valid_plan):
    base_valid_plan.day1_manual_action.operator_feedrate_dial_pct = 120
    all_passed, badges = verify_ppap_window(base_valid_plan, control_limits)
    assert all_passed is False
    feed_badge = next(b for b in badges if b["label"] == "Day-1 Feed Override Dial")
    assert feed_badge["passed"] is False


def test_ppap_sandbox_blocks_excessive_wear_offset(control_limits, base_valid_plan):
    base_valid_plan.day1_manual_action.m01_manual_wear_offset_z_microns = 48.0
    all_passed, _ = verify_ppap_window(base_valid_plan, control_limits)
    assert all_passed is True

    strict_limits = {"T03": dict(control_limits["T03"], max_wear_offset_microns=10.0)}
    all_passed_strict, badges = verify_ppap_window(base_valid_plan, strict_limits)
    assert all_passed_strict is False
    wear_badge = next(b for b in badges if b["label"] == "M01 Z-Wear Offset Ceiling")
    assert wear_badge["passed"] is False


def test_ppap_sandbox_blocks_rpm_window_violations(control_limits, base_valid_plan):
    base_valid_plan.tier2_focas_simulation.programmed_rpm_override = 2400
    all_passed, badges = verify_ppap_window(base_valid_plan, control_limits)
    assert all_passed is False
    rpm_badge = next(b for b in badges if b["label"] == "Tier-2 RPM Window")
    assert rpm_badge["passed"] is False


def test_ppap_sandbox_blocks_high_chipload_torque(control_limits, base_valid_plan):
    base_valid_plan.day1_manual_action.operator_feedrate_dial_pct = 110
    base_valid_plan.tier2_focas_simulation.programmed_rpm_override = 2800
    all_passed, badges = verify_ppap_window(base_valid_plan, control_limits)
    assert all_passed is False
    torque_badge = next(b for b in badges if b["label"] == "Spindle Chip-Load Torque")
    assert torque_badge["passed"] is False


def test_deterministic_control_plan_solver_clamps_physics_bounds(control_plan_limits):
    for chatter_hz in (2400.0, 4210.0, 6800.0, 12000.0):
        sol = solve_deterministic_control_plan(
            detected_chatter_hz=chatter_hz,
            spindle_rpm=3800,
            flute_count_z=2,
            target_tool_id="T03",
            control_plan_limits=control_plan_limits,
            requested_wear_offset_z_microns=85.0,  # deliberately over +-50um ceiling to test clamping
        )
        assert sol.all_passed is True
        assert 70 <= sol.operator_feedrate_dial_pct <= 110
        assert 80 <= sol.spindle_speed_dial_pct <= 115
        assert 0.65 <= sol.relative_chip_load_ratio <= 1.15
        assert abs(sol.m01_manual_wear_offset_z_microns) <= 50.0
        assert len(sol.verification_badges) == 4
        assert all(b.passed for b in sol.verification_badges)


def test_roi_calculator_and_48_day_hardware_payback(control_plan_limits):
    roi = calculate_remediation_roi(
        target_tool_id="T03",
        operator_feedrate_dial_pct=85,
        control_limits=control_plan_limits,
    )
    assert roi["casting_savings_inr"] == 14000
    assert roi["insert_savings_inr"] == 2200
    assert roi["estimated_savings_inr"] == 16200
    assert roi["hardware_payback_months"] == 1.6
    assert roi["hardware_payback_days"] == 48
    assert "1.6 months (~48 days)" in roi["payback_label"]

    payback = calculate_hardware_payback()
    assert payback["net_monthly_benefit_inr"] == 22000
    assert payback["hardware_payback_months"] == 1.6


def test_kms_certificate_service_signs_and_verifies_pillow_certificate():
    svc = KMSCertificateService()
    frame_bytes = Path("data/golden_references/REF-10.jpg").read_bytes()
    in_cycle = InCycleTelemetrySummary(
        cycle_id="CYC_CHAKAN_04_99280",
        stage_a_state="GREEN_NOMINAL",
        peak_vibration_rms_g=1.12,
        band_power_ratio_2k_8k=0.14,
        hilbert_envelope_coherence=0.19,
        chatter_detected=False,
    )
    aoi = AOIInspectionResult(
        cycle_id="CYC_CHAKAN_04_99280",
        passed_iatf_16949=False,
        matched_reference_token_id="REF-10",
        detected_anomaly_type="FOUNDRY_POROSITY_CHARGEBACK",
        surface_ra_estimate_um=1.14,
        inspector_summary="Foundry porosity with clean in-cycle vibration.",
        in_cycle_summary=in_cycle,
    )
    bundle = svc.render_certificate_png(
        part_id="DIFF_SN_001",
        work_order_id="WO_ALSI9CU3_DIFF_882",
        raw_frame_bytes=frame_bytes,
        aoi_result=aoi,
        in_cycle_summary=in_cycle,
    )
    assert bundle["certificate_png_bytes"][:8] == b"\x89PNG\r\n\x1a\n"
    assert len(bundle["raw_frame_sha256"]) == 64
    assert svc.verify_local_signature(bundle["canonical_payload_bytes"], bundle["kms_signature_b64"]) is True
    assert svc.verify_local_signature(bundle["canonical_payload_bytes"] + b"tampered", bundle["kms_signature_b64"]) is False
