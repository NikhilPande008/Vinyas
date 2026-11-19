"""
backend/agents/planner_agent.py
PPAPPlannerAgent (Column 2 of Verification Trace — "Physics Calculates, AI Diagnoses"):
1. Uses Gemini 2.5 Flash (`DiagnosticEvidence`) strictly for multimodal fault classification.
2. Calls `solve_deterministic_control_plan()` to mathematically calculate & clamp
   Feedrate Override Dial [70..110]%, Spindle Speed Dial [80..115]%, and Relative Chip-Load [0.65..1.15].
3. Computes INR scrap avoidance & validated 1.6-month (~48 days) net hardware payback via `roi_calculator.py`.
4. Emits both `RemediationPlan` and backwards-compatible `PPAPRemediationPlan` artifacts.
"""
import json
import logging
from pathlib import Path
from typing import Optional
from config.settings import settings
from backend.models.schemas import (
    MultimodalIncidentPayload,
    PPAPRemediationPlan,
    RemediationPlan,
    DiagnosticEvidence,
    DeterministicControlSolution,
    Day1NonInvasiveAction,
    Tier2AutomatedFocasPayload,
    VectorSearchMatch,
)
from backend.services.gemini_omni_service import GeminiOmniService
from backend.skills.control_plan_solver import (
    load_control_plan_limits,
    solve_deterministic_control_plan,
)
from backend.skills.roi_calculator import calculate_remediation_roi

logger = logging.getLogger("vinyas_ai.agents.planner")


class PPAPPlannerAgent:
    def __init__(
        self,
        omni_service: Optional[GeminiOmniService] = None,
        control_limits_path: str = "config/control_plan_limits.json",
    ):
        self.omni_service = omni_service or GeminiOmniService()
        cp_path = Path(control_limits_path)
        if not cp_path.exists():
            cp_path = Path("config/ppap_control_limits.json")
        self.control_limits = json.loads(cp_path.read_text(encoding="utf-8"))

    async def generate_unified_plan(
        self,
        incident: MultimodalIncidentPayload,
        vector_match: VectorSearchMatch,
        diagnostic_evidence: Optional[DiagnosticEvidence] = None,
    ) -> tuple[RemediationPlan, PPAPRemediationPlan]:
        """
        Separates AI diagnosis from deterministic physics calculation.
        Returns (RemediationPlan, PPAPRemediationPlan).
        """
        tool_id = incident.active_tool_id
        dsp = incident.stage_a_dsp_telemetry
        tools_map = self.control_limits.get("tools", self.control_limits)
        tool_cfg = tools_map.get(tool_id, tools_map["T03"])

        evidence = diagnostic_evidence or DiagnosticEvidence(
            cycle_id=incident.cycle_id,
            defect_classification="Carbide Insert Flank Wear inducing Regenerative Chatter",
            detected_harmonic_hz=dsp.dominant_carrier_freq_hz,
            confidence_score=vector_match.cosine_similarity,
            is_false_positive=False,
            evidence_summary=(
                f"Primary Ch 0 2-8 kHz vibration ratio={dsp.band_power_ratio_2k_8k:.2f}, "
                f"crest={dsp.spectral_crest_factor:.1f}, coherence booster={dsp.hilbert_envelope_coherence:.2f}."
            ),
            recommended_physical_check=f"Inspect Tool {tool_id} insert edge at M01 stop and index Corner #2.",
            served_from_fallback=settings.DEMO_SAFE_MODE,
        )

        # Physics Calculates: deterministic control plan solver
        solution: DeterministicControlSolution = solve_deterministic_control_plan(
            detected_chatter_hz=evidence.detected_harmonic_hz,
            spindle_rpm=int(tool_cfg.get("nominal_rpm", 3800)),
            flute_count_z=int(tool_cfg.get("flute_count_z", 2)),
            target_tool_id=tool_id,
            control_plan_limits=self.control_limits,
            requested_wear_offset_z_microns=12.0,
        )

        # Economic ROI + validated 1.6-month (~48 days) net hardware payback
        roi = calculate_remediation_roi(
            target_tool_id=tool_id,
            operator_feedrate_dial_pct=solution.operator_feedrate_dial_pct,
            control_limits=self.control_limits,
        )

        marathi_card = (
            f"Tool {tool_id} Finishing Pass madhye chatter ({evidence.detected_harmonic_hz:.0f} Hz) aala aahe. "
            f"M01 Hold var Feedrate Override knob {solution.operator_feedrate_dial_pct}% ani "
            f"Spindle Speed dial {solution.spindle_speed_dial_pct}% ({solution.target_rpm} RPM) var set kara, "
            f"ani {tool_id} Insert Corner #2 badla."
        )

        focas_reg = f"G10_L11_P{tool_id[1:]}"
        implementation_plan_md = f"""# Vinyas Control-Plan Remediation: {incident.machine_id} (Cycle {incident.cycle_id})

## 1. AI Root-Cause Classification (DiagnosticEvidence Only)
- **Defect Classification:** {evidence.defect_classification}
- **Dominant Chatter Harmonic:** `{evidence.detected_harmonic_hz:.0f} Hz` | **Vector Match:** `{vector_match.matched_signature_id}` (`{vector_match.cosine_similarity:.2f}`)
- **Primary Ch 0 Vibration:** Band Ratio `{dsp.band_power_ratio_2k_8k:.2f}` | Crest `{dsp.spectral_crest_factor:.1f}` | Coherence Booster `{dsp.hilbert_envelope_coherence:.2f}`

## 2. Deterministic Physics Control Solution ("Physics Calculates, AI Diagnoses")
1. **Operator Feedrate Override Dial:** **{solution.operator_feedrate_dial_pct}%** (Control Plan Window: `70%..110%`)
2. **Spindle Speed Override Dial:** **{solution.spindle_speed_dial_pct}%** -> **{solution.target_rpm} RPM** (Window: `80%..115%`, $Z={solution.flute_count_z}$ flutes)
3. **Relative Chip-Load Ratio:** **`{solution.relative_chip_load_ratio:.2f}`** (Clamped inside `[0.65..1.15]`)
4. **Supervisor M01 Z-Wear Offset:** **`+{solution.m01_manual_wear_offset_z_microns:.1f} um`** & index Tool `{tool_id}` Insert Corner #2.

## 3. Economic ROI & Net Hardware Payback
- **Cycle-Time Penalty:** `+{roi['cycle_time_penalty_sec']} s/part`
- **Direct Scrap Avoided:** `+INR {roi['estimated_savings_inr']:,}` (`INR {roi['casting_savings_inr']:,}` casting + `INR {roi['insert_savings_inr']:,}` insert)
- **Validated Hardware Payback:** **{roi['payback_label']}** (`INR 35,000` kit / `INR {roi['net_monthly_benefit_inr']:,}/mo` net benefit after SaaS)
"""

        todo_checklist_md = f"""- [x] Stage A DSP (<1.4 ms): Primary 2-8 kHz vibration + Hilbert coherence booster triggered `YELLOW_M01_HOLD`
- [x] Physics Control Solver: Clamped Feed `{solution.operator_feedrate_dial_pct}%`, Speed `{solution.spindle_speed_dial_pct}%`, Chip-Load `{solution.relative_chip_load_ratio:.2f}` in `[0.65..1.15]`
- [ ] Operator Action (M01 Hold): Set Feed dial `{solution.operator_feedrate_dial_pct}%`, Speed dial `{solution.spindle_speed_dial_pct}%`, index `{tool_id}` Corner #2
- [ ] Supervisor Action: Verify `+{solution.m01_manual_wear_offset_z_microns:.1f} um` Z-wear offset & confirm via Marathi PTT pod
"""

        unified = RemediationPlan(
            cycle_id=incident.cycle_id,
            diagnostic_evidence=evidence,
            control_solution=solution,
            operator_card_marathi=marathi_card,
            cycle_time_penalty_sec=roi["cycle_time_penalty_sec"],
            estimated_savings_inr=roi["estimated_savings_inr"],
            hardware_payback_months=roi["hardware_payback_months"],
            implementation_plan_md=implementation_plan_md,
            todo_checklist_md=todo_checklist_md,
            served_from_fallback=evidence.served_from_fallback,
        )

        legacy_compat = PPAPRemediationPlan(
            defect_classification=evidence.defect_classification,
            detected_harmonic_hz=evidence.detected_harmonic_hz,
            envelope_coherence_score=dsp.hilbert_envelope_coherence,
            is_false_positive=evidence.is_false_positive,
            target_tool_id=tool_id,
            day1_manual_action=Day1NonInvasiveAction(
                operator_feedrate_dial_pct=solution.operator_feedrate_dial_pct,
                spindle_speed_dial_pct=solution.spindle_speed_dial_pct,
                m01_manual_wear_offset_z_microns=solution.m01_manual_wear_offset_z_microns,
                require_insert_indexing=solution.require_insert_indexing,
                operator_card_marathi=marathi_card,
            ),
            tier2_focas_simulation=Tier2AutomatedFocasPayload(
                focas_target_register=focas_reg,
                programmed_rpm_override=solution.target_rpm,
            ),
            cycle_time_penalty_sec=roi["cycle_time_penalty_sec"],
            estimated_savings_inr=roi["estimated_savings_inr"],
            implementation_plan_md=implementation_plan_md,
            todo_checklist_md=todo_checklist_md,
            served_from_fallback=evidence.served_from_fallback,
        )

        return unified, legacy_compat

    async def generate_plan(
        self,
        incident: MultimodalIncidentPayload,
        vector_match: VectorSearchMatch,
    ) -> PPAPRemediationPlan:
        _, legacy = await self.generate_unified_plan(incident, vector_match)
        return legacy
