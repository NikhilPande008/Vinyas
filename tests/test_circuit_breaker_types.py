"""
tests/test_circuit_breaker_types.py
Verifies that @with_demo_circuit_breaker always returns validated instances of the
exact same Pydantic model (`response_model`) AND stamps `served_from_fallback`:
1. DEMO_SAFE_MODE = True -> returns validated Pydantic model with served_from_fallback=True
2. DEMO_SAFE_MODE = False with live return -> served_from_fallback=False
3. DEMO_SAFE_MODE = False with TimeoutError failover -> served_from_fallback=True
"""
import asyncio
import pytest
from config.settings import settings
from backend.models.schemas import (
    PPAPRemediationPlan,
    DiagnosticEvidence,
    AOIInspectionResult,
    SanitizedVoiceIntent,
)
from backend.services.circuit_breaker import with_demo_circuit_breaker


@pytest.mark.asyncio
async def test_circuit_breaker_safe_mode_returns_pydantic_models(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_SAFE_MODE", True)

    @with_demo_circuit_breaker("ppap_chatter_t03.json", response_model=PPAPRemediationPlan)
    async def mock_omni_call() -> PPAPRemediationPlan:
        raise AssertionError("Should not invoke live call when DEMO_SAFE_MODE is True")

    @with_demo_circuit_breaker("diagnostic_evidence_chatter_t03.json", response_model=DiagnosticEvidence)
    async def mock_evidence_call() -> DiagnosticEvidence:
        raise AssertionError("Should not invoke live call when DEMO_SAFE_MODE is True")

    @with_demo_circuit_breaker("aoi_pass_synthid.json", response_model=AOIInspectionResult)
    async def mock_aoi_call() -> AOIInspectionResult:
        raise AssertionError("Should not invoke live call when DEMO_SAFE_MODE is True")

    @with_demo_circuit_breaker("voice_confirm_insert_swap.json", response_model=SanitizedVoiceIntent)
    async def mock_voice_call() -> SanitizedVoiceIntent:
        raise AssertionError("Should not invoke live call when DEMO_SAFE_MODE is True")

    plan = await mock_omni_call()
    evidence = await mock_evidence_call()
    aoi = await mock_aoi_call()
    voice = await mock_voice_call()

    assert isinstance(plan, PPAPRemediationPlan)
    assert plan.served_from_fallback is True
    assert plan.target_tool_id == "T03"
    assert plan.day1_manual_action.operator_feedrate_dial_pct == 85

    assert isinstance(evidence, DiagnosticEvidence)
    assert evidence.served_from_fallback is True

    assert isinstance(aoi, AOIInspectionResult)
    assert aoi.served_from_fallback is True
    assert aoi.passed_iatf_16949 is True
    assert aoi.matched_reference_token_id == "REF-01"

    assert isinstance(voice, SanitizedVoiceIntent)
    assert voice.served_from_fallback is True
    assert voice.intent == "CONFIRM_INSERT_SWAP"


@pytest.mark.asyncio
async def test_circuit_breaker_live_and_timeout_failover_type_identity(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_SAFE_MODE", False)

    @with_demo_circuit_breaker(
        "aoi_foundry_porosity_ref10.json",
        response_model=AOIInspectionResult,
        timeout_sec=0.15,
    )
    async def slow_cloud_call() -> AOIInspectionResult:
        await asyncio.sleep(1.0)
        raise RuntimeError("Unreachable timeout")

    @with_demo_circuit_breaker(
        "aoi_foundry_porosity_ref10.json",
        response_model=AOIInspectionResult,
        timeout_sec=1.0,
    )
    async def live_dict_call() -> dict:
        return {
            "cycle_id": "CYC_LIVE_001",
            "passed_iatf_16949": False,
            "matched_reference_token_id": "REF-10",
            "detected_anomaly_type": "FOUNDRY_POROSITY_CHARGEBACK",
            "surface_ra_estimate_um": 1.14,
            "inspector_summary": "Live foundry porosity match",
            "raw_frame_hmac_sha256": "abc123",
        }

    fallback_res = await slow_cloud_call()
    live_res = await live_dict_call()

    assert type(fallback_res) is type(live_res)
    assert isinstance(fallback_res, AOIInspectionResult)
    assert isinstance(live_res, AOIInspectionResult)
    assert fallback_res.served_from_fallback is True
    assert live_res.served_from_fallback is False
    assert fallback_res.detected_anomaly_type == "FOUNDRY_POROSITY_CHARGEBACK"
    assert live_res.detected_anomaly_type == "FOUNDRY_POROSITY_CHARGEBACK"
