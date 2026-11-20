"""
backend/agents/orchestrator.py
Vinyas 4-Agent Verification Pipeline Orchestrator:
- Column 1: DiagnosticExtractorAgent (Mel-Spectrogram, anti-aliased 16 kHz WAV, Primary Ch 0 Vibration + Coherence, BigQuery 1408-d Vector Match)
- Column 2: PPAPPlannerAgent (AI DiagnosticEvidence + Deterministic Physics Control-Plan Solver + Gemma Vernacular Card + 1.6-mo ROI)
- Column 3: SandboxSafetyValidatorAgent (Deterministic Mathematical Assertion Badges)
"""
import base64
import logging
import time
import uuid
from typing import Optional
import numpy as np
from config.settings import settings
from backend.agents.extractor_agent import DiagnosticExtractorAgent
from backend.agents.planner_agent import PPAPPlannerAgent
from backend.agents.validator_agent import SandboxSafetyValidatorAgent
from backend.agents.executor_agent import ShopFloorExecutorAgent
from backend.models.schemas import (
    MultimodalIncidentPayload,
    PipelineObservabilityTrace,
    ThreeColumnTraceResponse,
)

logger = logging.getLogger("vinyas_ai.agents.orchestrator")


class AntigravityPipelineOrchestrator:
    def __init__(
        self,
        extractor: Optional[DiagnosticExtractorAgent] = None,
        planner: Optional[PPAPPlannerAgent] = None,
        validator: Optional[SandboxSafetyValidatorAgent] = None,
        executor: Optional[ShopFloorExecutorAgent] = None,
    ):
        self.extractor = extractor or DiagnosticExtractorAgent()
        self.planner = planner or PPAPPlannerAgent()
        self.validator = validator or SandboxSafetyValidatorAgent()
        self.executor = executor or ShopFloorExecutorAgent()

    async def run_incident_pipeline(
        self,
        incident: MultimodalIncidentPayload,
        stereo_chunk_raw: Optional[np.ndarray] = None,
    ) -> ThreeColumnTraceResponse:
        t0_pipeline = time.perf_counter()

        # Column 1: Feature extraction, BigQuery + 1408-d NumPy vector search, Mel-spectrogram, and 16 kHz WAV bundle
        vector_match, mel_b64, mel_png_bytes, wav_16k_bytes = await self.extractor.extract_and_match_bundle(
            incident, stereo_chunk_raw
        )
        incident.vector_search_match = vector_match

        # Column 2: AI classification (real WAV + PNG) + Deterministic Physics Control-Plan Solver + Gemma Vernacular Card
        unified_plan, compat_plan = await self.planner.generate_unified_plan(
            incident=incident,
            vector_match=vector_match,
            audio_wav_16k_bytes=wav_16k_bytes,
            mel_spectrogram_png_bytes=mel_png_bytes,
        )

        # Column 3: Deterministic verification badges (combining physics solver badges + PPAP window)
        legacy_passed, _legacy_badges = self.validator.validate_plan(compat_plan)
        solver_badges = unified_plan.control_solution.verification_badges
        all_passed = unified_plan.control_solution.all_passed and legacy_passed

        total_pipeline_ms = round((time.perf_counter() - t0_pipeline) * 1000.0, 2)
        vernacular_card = getattr(self.planner, "last_vernacular_card", None)
        observability = PipelineObservabilityTrace(
            request_id=f"req_{uuid.uuid4().hex[:10]}",
            stage_a_dsp_latency_ms=incident.stage_a_dsp_telemetry.execution_latency_ms,
            stage_b_gemma_latency_ms=incident.stage_b_gemma_triage.triage_latency_ms,
            vector_search_latency_ms=vector_match.query_latency_ms,
            gemini_diagnostic_latency_ms=getattr(self.planner, "last_gemini_diagnostic_latency_ms", 0.0),
            physics_solver_latency_ms=getattr(self.planner, "last_solver_latency_ms", 0.15),
            gemma_vernacular_latency_ms=(
                vernacular_card.translation_latency_ms if vernacular_card else 0.0
            ),
            total_pipeline_latency_ms=total_pipeline_ms,
            routing_path=vector_match.routing_path,
            cloud_sync_status=(
                "LOCAL_LEDGER_CACHED"
                if (settings.DEMO_SAFE_MODE or unified_plan.served_from_fallback)
                else "LIVE_BIGQUERY_STREAMED"
            ),
        )

        return ThreeColumnTraceResponse(
            incident=incident,
            vector_match=vector_match,
            diagnostic_evidence=unified_plan.diagnostic_evidence,
            control_solution=unified_plan.control_solution,
            vernacular_card=vernacular_card,
            observability=observability,
            remediation_plan=compat_plan,
            unified_plan=unified_plan,
            ppap_all_passed=all_passed,
            ppap_badges=solver_badges,
            mel_spectrogram_b64=mel_b64,
            audio_wav_16k_b64=base64.b64encode(wav_16k_bytes).decode("ascii"),
            safe_mode_active=settings.DEMO_SAFE_MODE,
            served_from_fallback=unified_plan.served_from_fallback,
            hardware_source="LIVE_USB" if settings.HARDWARE_SOURCE == "USB_STEREO_ADC" else "SIMULATED",
        )
