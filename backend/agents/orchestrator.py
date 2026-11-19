"""
backend/agents/orchestrator.py
Vinyas 4-Agent Verification Pipeline Orchestrator:
- Column 1: DiagnosticExtractorAgent (Mel-Spectrogram, Primary Ch 0 Vibration + Coherence, Vector Match)
- Column 2: PPAPPlannerAgent (AI DiagnosticEvidence + Deterministic Physics Control-Plan Solver + 1.6-mo ROI)
- Column 3: SandboxSafetyValidatorAgent (Deterministic Mathematical Assertion Badges)
"""
import logging
from typing import Optional
import numpy as np
from config.settings import settings
from backend.agents.extractor_agent import DiagnosticExtractorAgent
from backend.agents.planner_agent import PPAPPlannerAgent
from backend.agents.validator_agent import SandboxSafetyValidatorAgent
from backend.agents.executor_agent import ShopFloorExecutorAgent
from backend.models.schemas import (
    MultimodalIncidentPayload,
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
        # Column 1: Feature extraction, vector search, Mel-spectrogram
        vector_match, mel_b64 = await self.extractor.extract_and_match(incident, stereo_chunk_raw)
        incident.vector_search_match = vector_match

        # Column 2: AI classification + Deterministic Physics Control-Plan Solver
        unified_plan, compat_plan = await self.planner.generate_unified_plan(incident, vector_match)

        # Column 3: Deterministic verification badges (combining physics solver badges + PPAP window)
        legacy_passed, _legacy_badges = self.validator.validate_plan(compat_plan)
        solver_badges = unified_plan.control_solution.verification_badges
        all_passed = unified_plan.control_solution.all_passed and legacy_passed

        return ThreeColumnTraceResponse(
            incident=incident,
            vector_match=vector_match,
            diagnostic_evidence=unified_plan.diagnostic_evidence,
            control_solution=unified_plan.control_solution,
            remediation_plan=compat_plan,
            unified_plan=unified_plan,
            ppap_all_passed=all_passed,
            ppap_badges=solver_badges,
            mel_spectrogram_b64=mel_b64,
            safe_mode_active=settings.DEMO_SAFE_MODE,
            served_from_fallback=unified_plan.served_from_fallback,
            hardware_source="LIVE_USB" if settings.HARDWARE_SOURCE == "USB_STEREO_ADC" else "SIMULATED",
        )
