"""
backend/models/schemas.py
Strict Pydantic V2 data contracts for Vinyas 4-Tier Architecture:
- InCycleTelemetrySummary (linked by cycle_id to post-cycle AOI)
- DiagnosticEvidence (AI classification only — "Physics Calculates, AI Diagnoses")
- DeterministicControlSolution (physics solver outputs clamped to Control Plan limits)
- RemediationPlan & PPAPRemediationPlan (with served_from_fallback tracking)
- AOIInspectionResult (linking cycle_id to separate REF-04 CNC chatter vs REF-10 Foundry Porosity)
- SanitizedVoiceIntent (vernacular PTT gate)
"""
from typing import Literal, Optional
from pydantic import BaseModel, Field


class SandboxVerificationBadge(BaseModel):
    label: str
    passed: bool
    detail: str


class InCycleTelemetrySummary(BaseModel):
    cycle_id: str = Field(default="CYC_CHAKAN_04_99281")
    machine_id: str = Field(default="FANUC_0iTF_CHAKAN_04")
    tool_id: Literal["T01", "T02", "T03", "T04"] = Field(default="T03")
    stage_a_state: Literal[
        "GREEN_NOMINAL",
        "GREEN_FALSE_POSITIVE_REJECTED",
        "YELLOW_M01_HOLD",
        "RED_PREEMPT",
    ] = Field(default="GREEN_NOMINAL")
    peak_vibration_rms_g: float = Field(ge=0.0, default=1.2)
    band_power_ratio_2k_8k: float = Field(ge=0.0, le=1.0, default=0.18)
    spectral_crest_factor: float = Field(ge=0.0, default=2.1)
    hilbert_envelope_coherence: float = Field(ge=0.0, le=1.0, default=0.15)
    ct_ripple_std_amps: float = Field(ge=0.0, default=0.25)
    dominant_chatter_hz: float = Field(ge=0.0, le=24000.0, default=4210.0)
    chatter_detected: bool = Field(default=False)


class DiagnosticEvidence(BaseModel):
    """
    Pure multimodal classification emitted by Gemini 2.5 Flash.
    Never guesses CNC offsets or overrides — physics calculation belongs strictly
    to `backend/skills/control_plan_solver.py`.
    """
    cycle_id: str = Field(default="CYC_CHAKAN_04_99281")
    defect_classification: str
    detected_harmonic_hz: float = Field(ge=0.0, le=24000.0)
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.94)
    is_false_positive: bool = Field(default=False)
    evidence_summary: str
    recommended_physical_check: str = Field(
        default="Inspect Tool T03 carbide insert flank edge at M01 optional stop."
    )
    served_from_fallback: bool = Field(default=False)


class DeterministicControlSolution(BaseModel):
    """
    Deterministic physics calculation emitted by `control_plan_solver.py`.
    All dial percentages and relative chip-load ratios are mathematically clamped
    to signed Control Plan limits (`[70, 110]%` feed, `[80, 115]%` spindle speed,
    `[0.65, 1.15]` relative chip-load ratio).
    """
    target_tool_id: Literal["T01", "T02", "T03", "T04"] = Field(default="T03")
    operator_feedrate_dial_pct: int = Field(ge=70, le=110)
    spindle_speed_dial_pct: int = Field(ge=80, le=115)
    nominal_rpm: int = Field(ge=500, le=12000)
    target_rpm: int = Field(ge=500, le=12000)
    flute_count_z: int = Field(ge=1, le=12, default=2)
    relative_chip_load_ratio: float = Field(ge=0.65, le=1.15)
    m01_manual_wear_offset_z_microns: float = Field(ge=-50.0, le=50.0, default=12.0)
    require_insert_indexing: bool = Field(default=True)
    all_passed: bool = Field(default=True)
    verification_badges: list[SandboxVerificationBadge] = Field(default_factory=list)


class RemediationPlan(BaseModel):
    """
    Unified Vinyas Remediation Plan combining AI DiagnosticEvidence with the
    DeterministicControlSolution, vernacular operator action card, and ROI math.
    """
    cycle_id: str = Field(default="CYC_CHAKAN_04_99281")
    diagnostic_evidence: DiagnosticEvidence
    control_solution: DeterministicControlSolution
    operator_card_marathi: str
    cycle_time_penalty_sec: float = Field(ge=0.0, le=60.0)
    estimated_savings_inr: int = Field(ge=0)
    hardware_payback_months: float = Field(ge=0.0, default=1.6)
    implementation_plan_md: str
    todo_checklist_md: str
    served_from_fallback: bool = Field(default=False)


class Day1NonInvasiveAction(BaseModel):
    operator_feedrate_dial_pct: int = Field(
        ge=50,
        le=120,
        description="Physical feedrate override dial setting (%) for Operator on Day-1 rig",
    )
    spindle_speed_dial_pct: int = Field(
        default=90,
        ge=70,
        le=125,
        description="Physical spindle speed override dial setting (%) for Operator",
    )
    m01_manual_wear_offset_z_microns: float = Field(
        ge=-50.0,
        le=50.0,
        description="Manual Z wear offset (microns) entered by Supervisor at M01 optional stop",
    )
    require_insert_indexing: bool = Field(
        description="True if operator must rotate/index carbide insert edge at cycle end"
    )
    operator_card_marathi: str = Field(
        description="Zero-jargon Marathi/Hinglish instruction shown on Operator Action Card"
    )


class Tier2AutomatedFocasPayload(BaseModel):
    focas_target_register: str = Field(
        default="G10_L11_P03", description="Optional CNC register for Tier-2 write"
    )
    programmed_rpm_override: int = Field(ge=500, le=12000)


class AOIInspectionResult(BaseModel):
    cycle_id: str = Field(
        default="CYC_CHAKAN_04_99281",
        description="Links post-cycle optical inspection to in-cycle vibration telemetry",
    )
    passed_iatf_16949: bool
    matched_reference_token_id: str = Field(
        description="Closest token ID from 14 cached references e.g. REF-01, REF-04, REF-10, REF-12"
    )
    detected_anomaly_type: Literal[
        "NONE_GOLDEN",
        "HARMLESS_OIL_DROPLET",
        "MICRO_BURR_REJECT",
        "CHATTER_SCAR_REJECT",
        "FOUNDRY_POROSITY_CHARGEBACK",
    ]
    surface_ra_estimate_um: float = Field(ge=0.1, le=12.5)
    inspector_summary: str
    in_cycle_summary: Optional[InCycleTelemetrySummary] = None
    raw_frame_sha256: str = ""
    raw_frame_hmac_sha256: str = ""
    kms_signature_b64: str = ""
    served_from_fallback: bool = Field(default=False)


class PPAPRemediationPlan(BaseModel):
    defect_classification: str
    detected_harmonic_hz: float = Field(ge=0.0, le=24000.0)
    envelope_coherence_score: float = Field(ge=0.0, le=1.0)
    is_false_positive: bool
    target_tool_id: Literal["T01", "T02", "T03", "T04"]
    day1_manual_action: Day1NonInvasiveAction
    tier2_focas_simulation: Tier2AutomatedFocasPayload
    cycle_time_penalty_sec: float = Field(ge=0.0, le=60.0)
    estimated_savings_inr: int = Field(ge=0)
    implementation_plan_md: str
    todo_checklist_md: str
    served_from_fallback: bool = Field(default=False)


class SanitizedVoiceIntent(BaseModel):
    intent: Literal[
        "CONFIRM_INSERT_SWAP",
        "REQUEST_SUPERVISOR",
        "EXPLAIN_HOLD",
        "IGNORE_NOISE",
    ]
    spoken_response_marathi: str = Field(
        description="Concise Marathi/Hinglish audio response to operator"
    )
    served_from_fallback: bool = Field(default=False)


class StageADSPTelemetry(BaseModel):
    cycle_id: str = Field(default="CYC_CHAKAN_04_99281")
    stage_a_state: Literal[
        "GREEN_NOMINAL",
        "GREEN_FALSE_POSITIVE_REJECTED",
        "YELLOW_M01_HOLD",
        "RED_PREEMPT",
    ]
    execution_latency_ms: float = Field(ge=0.0)
    ae_rms_g: float = Field(ge=0.0)
    ct_ripple_std_amps: float = Field(ge=0.0)
    band_power_ratio_2k_8k: float = Field(default=0.62, ge=0.0, le=1.0)
    spectral_crest_factor: float = Field(default=7.4, ge=0.0)
    hilbert_envelope_coherence: float = Field(ge=0.0, le=1.0)
    dominant_carrier_freq_hz: float = Field(default=4210.0, ge=0.0, le=24000.0)
    modulation_sideband_hz: float = Field(default=68.5, ge=0.0, le=1000.0)


class StageBGemmaTriage(BaseModel):
    model_id: str = Field(default="gemma-3n-E4B-it")
    triage_latency_ms: float = Field(ge=0.0)
    is_transient_entry: bool
    escalate_to_cloud: bool
    edge_summary: str


class VectorSearchMatch(BaseModel):
    matched_signature_id: str
    cosine_similarity: float = Field(ge=0.0, le=1.0)
    nominal_baseline_similarity: float = Field(default=0.74, ge=0.0, le=1.0)
    routing_path: Literal["LOCAL_EDGE_FAST_PATH", "CLOUD_GEMINI_ESCALATION"] = Field(
        default="CLOUD_GEMINI_ESCALATION"
    )
    search_backend: str = Field(default="BIGQUERY_1408D_NUMPY_COSINE_CACHE")
    query_latency_ms: float = Field(default=0.42, ge=0.0)


class MultimodalIncidentPayload(BaseModel):
    event_id: str
    cycle_id: str = Field(default="CYC_CHAKAN_04_99281")
    timestamp_utc: str
    machine_id: str = Field(default="FANUC_0iTF_CHAKAN_04")
    work_order_id: str = Field(default="WO_ALSI9CU3_DIFF_882")
    active_tool_id: Literal["T01", "T02", "T03", "T04"] = Field(default="T03")
    stage_a_dsp_telemetry: StageADSPTelemetry
    stage_b_gemma_triage: StageBGemmaTriage
    vector_search_match: Optional[VectorSearchMatch] = None


class VernacularActionCard(BaseModel):
    """
    Zero-jargon vernacular operator action cards translated from pre-verified
    `DeterministicControlSolution` parameters by Gemma (`gemma-3-4b-it`).
    Never alters the numerical feed/speed/wear values computed by `control_plan_solver.py`.
    """
    model_id: str = Field(default="gemma-3-4b-it")
    marathi: str = Field(
        description="Concise zero-jargon Marathi operator instruction containing the exact feed %, speed %, and tool corner"
    )
    hindi: str = Field(
        description="Concise zero-jargon Hindi operator instruction containing the exact feed %, speed %, and tool corner"
    )
    hinglish: str = Field(
        description="Concise shop-floor Hinglish operator instruction containing the exact feed %, speed %, and tool corner"
    )
    translation_latency_ms: float = Field(default=12.4, ge=0.0)
    served_from_fallback: bool = Field(default=False)


class PipelineObservabilityTrace(BaseModel):
    """Real-time stage-by-stage latency and routing telemetry exposed to technical jurors."""
    request_id: str = Field(default="req_vinyas_live")
    stage_a_dsp_latency_ms: float = Field(default=0.48, ge=0.0)
    stage_b_gemma_latency_ms: float = Field(default=42.1, ge=0.0)
    vector_search_latency_ms: float = Field(default=0.35, ge=0.0)
    gemini_diagnostic_latency_ms: float = Field(default=0.0, ge=0.0)
    physics_solver_latency_ms: float = Field(default=0.18, ge=0.0)
    gemma_vernacular_latency_ms: float = Field(default=12.4, ge=0.0)
    total_pipeline_latency_ms: float = Field(default=55.5, ge=0.0)
    routing_path: Literal["LOCAL_EDGE_FAST_PATH", "CLOUD_GEMINI_ESCALATION"] = Field(
        default="CLOUD_GEMINI_ESCALATION"
    )
    cloud_sync_status: Literal["LIVE_BIGQUERY_STREAMED", "LOCAL_LEDGER_CACHED"] = Field(
        default="LOCAL_LEDGER_CACHED"
    )


class ThreeColumnTraceResponse(BaseModel):
    incident: MultimodalIncidentPayload
    vector_match: VectorSearchMatch
    diagnostic_evidence: Optional[DiagnosticEvidence] = None
    control_solution: Optional[DeterministicControlSolution] = None
    vernacular_card: Optional[VernacularActionCard] = None
    observability: Optional[PipelineObservabilityTrace] = None
    remediation_plan: PPAPRemediationPlan
    unified_plan: Optional[RemediationPlan] = None
    ppap_all_passed: bool
    ppap_badges: list[SandboxVerificationBadge]
    mel_spectrogram_b64: Optional[str] = None
    audio_wav_16k_b64: Optional[str] = None
    safe_mode_active: bool = False
    served_from_fallback: bool = False
    hardware_source: str = Field(default="WAV_REPLAY")
