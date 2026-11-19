"""
backend/main.py
FastAPI Lifespan and Control Plane for Vinyas (Startup Buildathon India 2026):
- Initializes 14-reference Drawing Spec & IATF 16949 Context Cache on startup
- Maintains in-cycle telemetry registry keyed by `cycle_id` to separate REF-04 CNC chatter
  from REF-10 Upstream Foundry Porosity Chargebacks
- Exposes `/api/v1/demo/toggle-safe-mode` and `/api/v1/relay/toggle-mode`
  (`DAY1_ANDON_ONLY` vs `DAY30_EXT_FEED_HOLD_CUTOUT`)
- Exposes `/api/v1/aoi/certificate` issuing ECDSA P-256 / Cloud KMS signed Pillow PNGs
"""
import base64
import contextlib
import logging
import sys
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.settings import settings
from edge.hardware_relay import HardwareRelayController
from backend.agents.orchestrator import AntigravityPipelineOrchestrator
from backend.models.schemas import (
    MultimodalIncidentPayload,
    ThreeColumnTraceResponse,
    AOIInspectionResult,
    InCycleTelemetrySummary,
    SanitizedVoiceIntent,
)
from backend.services.bigquery_logger import BigQueryLogger
from backend.services.gemini_live_service import GeminiLiveService
from backend.services.kms_certificate_service import KMSCertificateService
from backend.services.lyria_synth_service import LyriaSynthService
from backend.services.nanobanana_aoi_service import NanoBananaAOIService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vinyas_ai.backend.main")

# Shared service instances
kms_cert_service = KMSCertificateService()
aoi_service = NanoBananaAOIService(kms_service=kms_cert_service)
live_service = GeminiLiveService()
lyria_service = LyriaSynthService()
bigquery_logger = BigQueryLogger()
relay_controller = HardwareRelayController()
orchestrator = AntigravityPipelineOrchestrator()

# In-cycle telemetry store keyed by cycle_id for post-cycle AOI correlation
IN_CYCLE_TELEMETRY_STORE: dict[str, InCycleTelemetrySummary] = {
    "CYC_CHAKAN_04_99280": InCycleTelemetrySummary(
        cycle_id="CYC_CHAKAN_04_99280",
        machine_id="FANUC_0iTF_CHAKAN_04",
        tool_id="T03",
        stage_a_state="GREEN_NOMINAL",
        peak_vibration_rms_g=1.15,
        band_power_ratio_2k_8k=0.14,
        spectral_crest_factor=2.3,
        hilbert_envelope_coherence=0.21,
        ct_ripple_std_amps=0.28,
        dominant_chatter_hz=1200.0,
        chatter_detected=False,
    ),
    "CYC_CHAKAN_04_99281": InCycleTelemetrySummary(
        cycle_id="CYC_CHAKAN_04_99281",
        machine_id="FANUC_0iTF_CHAKAN_04",
        tool_id="T03",
        stage_a_state="YELLOW_M01_HOLD",
        peak_vibration_rms_g=2.84,
        band_power_ratio_2k_8k=0.71,
        spectral_crest_factor=8.2,
        hilbert_envelope_coherence=0.84,
        ct_ripple_std_amps=0.46,
        dominant_chatter_hz=4210.0,
        chatter_detected=True,
    ),
}


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Vinyas Control Plane Lifespan...")
    try:
        cache_name = aoi_service.initialize_14_reference_cache()
        logger.info("Pinned 14-Reference Context Cache: %s", cache_name)
    except Exception as exc:
        logger.warning("Cache pre-warming notice: %s", exc)
    yield
    relay_controller.close()
    logger.info("Shutting down Vinyas Control Plane.")


app = FastAPI(
    title="Vinyas Control Plane",
    version="2.2.0",
    description="Edge-to-Cloud Acoustic-Electrical & Polarized Optical Digital Twin (Team Vinyas)",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class VoiceRequest(BaseModel):
    utterance: str
    machine_state: str = "YELLOW_M01_HOLD"
    context: Optional[dict[str, Any]] = None


class AOIRequest(BaseModel):
    part_id: str = "PART_ALSI9CU3_DIFF_992"
    work_order_id: str = "WO_ALSI9CU3_DIFF_882"
    cycle_id: str = "CYC_CHAKAN_04_99281"
    acoustic_rms: float = 1.15
    image_b64: Optional[str] = None


class FaultSynthesizeRequest(BaseModel):
    fault_type: str = "CHATTER_4210HZ"
    duration_sec: float = 2.0


class DefectSynthRequest(BaseModel):
    defect_type: str = "MICRO_BURR_REJECT"
    base_token_id: str = "REF-01"


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "vinyas-ai-v2.1",
        "demo_safe_mode": settings.DEMO_SAFE_MODE,
        "hardware_source": "LIVE_USB" if settings.HARDWARE_SOURCE == "USB_STEREO_ADC" else "SIMULATED",
        "relay_operating_mode": relay_controller.operating_mode,
        "sample_rate_hz": settings.SAMPLE_RATE_HZ,
        "omni_model": settings.GEMINI_OMNI_MODEL_ID,
        "image_model": settings.GEMINI_IMAGE_MODEL_ID,
    }


@app.post("/api/v1/demo/toggle-safe-mode")
async def toggle_demo_safe_mode():
    settings.DEMO_SAFE_MODE = not settings.DEMO_SAFE_MODE
    new_state = "SAFE" if settings.DEMO_SAFE_MODE else "LIVE"
    logger.info("DEMO_SAFE_MODE toggled to: %s", new_state)
    return {
        "status": "success",
        "demo_safe_mode": settings.DEMO_SAFE_MODE,
        "mode_label": new_state,
        "message": f"Circuit breaker mode switched to {new_state}.",
    }


@app.post("/api/v1/relay/toggle-mode")
async def toggle_relay_operating_mode():
    """Switches relay between Mode 1 (DAY1_ANDON_ONLY) and Mode 2 (DAY30_EXT_FEED_HOLD_CUTOUT)."""
    new_mode = relay_controller.toggle_operating_mode()
    return {
        "status": "success",
        "relay_operating_mode": new_mode,
        "ext_feed_hold_engaged": relay_controller.ext_feed_hold_engaged,
        "hardware_connected": relay_controller.hardware_connected,
    }


@app.post("/api/v1/incidents/process", response_model=ThreeColumnTraceResponse)
async def process_incident(incident: MultimodalIncidentPayload):
    try:
        dsp = incident.stage_a_dsp_telemetry
        IN_CYCLE_TELEMETRY_STORE[incident.cycle_id] = InCycleTelemetrySummary(
            cycle_id=incident.cycle_id,
            machine_id=incident.machine_id,
            tool_id=incident.active_tool_id,
            stage_a_state=dsp.stage_a_state,
            peak_vibration_rms_g=dsp.ae_rms_g,
            band_power_ratio_2k_8k=dsp.band_power_ratio_2k_8k,
            spectral_crest_factor=dsp.spectral_crest_factor,
            hilbert_envelope_coherence=dsp.hilbert_envelope_coherence,
            ct_ripple_std_amps=dsp.ct_ripple_std_amps,
            dominant_chatter_hz=dsp.dominant_carrier_freq_hz,
            chatter_detected=(dsp.stage_a_state in ("YELLOW_M01_HOLD", "RED_PREEMPT")),
        )

        response = await orchestrator.run_incident_pipeline(incident)
        await bigquery_logger.log_incident(
            {
                "event_id": incident.event_id,
                "cycle_id": incident.cycle_id,
                "machine_id": incident.machine_id,
                "tool_id": incident.active_tool_id,
                "state": dsp.stage_a_state,
                "coherence": dsp.hilbert_envelope_coherence,
                "ppap_passed": response.ppap_all_passed,
                "estimated_savings_inr": response.remediation_plan.estimated_savings_inr,
                "cycle_time_penalty_sec": response.remediation_plan.cycle_time_penalty_sec,
            }
        )
        return response
    except Exception as exc:
        logger.exception("Incident processing failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/voice/interact", response_model=SanitizedVoiceIntent)
async def voice_interaction(req: VoiceRequest):
    intent = await live_service.process_operator_utterance(
        operator_utterance=req.utterance,
        current_machine_state=req.machine_state,
    )
    if intent.intent == "CONFIRM_INSERT_SWAP" and req.context:
        relay_controller.trigger_green_nominal()
        await bigquery_logger.log_incident(
            {
                "event_id": req.context.get("event_id", "evt_voice_action"),
                "machine_id": req.context.get("machine_id", "FANUC_0iTF_CHAKAN_04"),
                "tool_id": req.context.get("tool_id", "T03"),
                "state": "ACTION_CONFIRMED_GREEN",
                "coherence": 0.0,
                "ppap_passed": True,
                "estimated_savings_inr": req.context.get("estimated_savings_inr", 16200),
                "cycle_time_penalty_sec": req.context.get("cycle_time_penalty_sec", 4.2),
            }
        )
    return intent


@app.post("/api/v1/aoi/inspect", response_model=AOIInspectionResult)
async def aoi_inspect(req: AOIRequest):
    image_bytes = (
        base64.b64decode(req.image_b64)
        if req.image_b64
        else b"sample_jpeg_placeholder"
    )
    in_cycle = IN_CYCLE_TELEMETRY_STORE.get(req.cycle_id)
    return await aoi_service.inspect_vblock_part(
        part_jpeg_bytes=image_bytes,
        acoustic_rms=req.acoustic_rms,
        work_order_id=req.work_order_id,
        cycle_id=req.cycle_id,
        in_cycle_summary=in_cycle,
    )


@app.post("/api/v1/aoi/certificate")
async def generate_signed_aoi_certificate(req: AOIRequest):
    """Generates a Pillow QA / Foundry Chargeback Certificate PNG signed via Cloud KMS / ECDSA P-256."""
    image_bytes = (
        base64.b64decode(req.image_b64)
        if req.image_b64
        else Path("data/golden_references/REF-10.jpg").read_bytes()
    )
    in_cycle = IN_CYCLE_TELEMETRY_STORE.get(req.cycle_id)
    aoi_res = await aoi_service.inspect_vblock_part(
        part_jpeg_bytes=image_bytes,
        acoustic_rms=req.acoustic_rms,
        work_order_id=req.work_order_id,
        cycle_id=req.cycle_id,
        in_cycle_summary=in_cycle,
    )
    cert_bundle = kms_cert_service.render_certificate_png(
        part_id=req.part_id,
        work_order_id=req.work_order_id,
        raw_frame_bytes=image_bytes,
        aoi_result=aoi_res,
        in_cycle_summary=aoi_res.in_cycle_summary,
    )
    return {
        "cycle_id": cert_bundle["cycle_id"],
        "raw_frame_sha256": cert_bundle["raw_frame_sha256"],
        "kms_signature_b64": cert_bundle["kms_signature_b64"],
        "signing_backend": cert_bundle["signing_backend"],
        "certificate_png_b64": base64.b64encode(cert_bundle["certificate_png_bytes"]).decode("ascii"),
    }


@app.post("/api/v1/faults/synthesize")
async def synthesize_fault(req: FaultSynthesizeRequest):
    wav_bytes, meta = lyria_service.synthesize_fault_stem(
        fault_type=req.fault_type,
        duration_sec=req.duration_sec,
    )
    return {
        "metadata": meta,
        "wav_b64": base64.b64encode(wav_bytes).decode("utf-8"),
    }


@app.post("/api/v1/faults/synthesize-defect")
async def synthesize_day0_defect(req: DefectSynthRequest):
    ref_path = settings.GOLDEN_REFS_DIR / f"{req.base_token_id}.jpg"
    if not ref_path.exists():
        ref_path = settings.GOLDEN_REFS_DIR / "REF-01.jpg"
    synth_bytes = await aoi_service.synthesize_cold_start_defect(
        base_golden_jpeg_bytes=ref_path.read_bytes(),
        defect_type=req.defect_type,
    )
    return {
        "defect_type": req.defect_type,
        "model_id": settings.GEMINI_IMAGE_MODEL_ID,
        "image_b64": base64.b64encode(synth_bytes).decode("ascii"),
    }


@app.get("/api/v1/telemetry/shift-aggregates")
async def get_shift_telemetry():
    return bigquery_logger.get_shift_economic_aggregates()
