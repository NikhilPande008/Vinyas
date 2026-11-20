"""Vinyas — Strict Pydantic v2 Data Contracts (`backend/schemas.py`)."""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class ModelAttempt(BaseModel):
    """Exact record of a single model invocation attempt."""

    model_id: str
    status: Literal[
        "OK",
        "TIMEOUT",
        "HTTP_429",
        "HTTP_503",
        "ERROR",
        "SCHEMA_INVALID",
        "SKIPPED",
    ]
    latency_ms: int = Field(..., ge=0)
    error: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class StageProvenance(BaseModel):
    """Truthful provenance for every pipeline stage."""

    stage: str
    producer: Literal["MODEL", "DETERMINISTIC", "FALLBACK_RULES", "FALLBACK_MODEL", "SKIPPED"]
    model_id: Optional[str] = None
    attempts: list[ModelAttempt] = Field(default_factory=list)
    latency_ms: int = Field(..., ge=0)
    input_simulated: bool = True
    note: Optional[str] = None


class SensorTelemetry(BaseModel):
    """Shop-floor machine sensor telemetry associated with an inspection cycle."""

    vibration_khz: float = Field(default=0.0, ge=0.0, description="Dominant frequency in kHz")
    vibration_rms_mms: float = Field(default=0.8, ge=0.0, description="Vibration velocity mm/s RMS (ISO 20816-3 reference)")
    temperature_c: float = Field(default=35.0, ge=0.0, description="Component or spindle housing temperature in °C")
    line_speed_rpm: int = Field(default=0, ge=0, description="Spindle RPM or line index speed")
    shielding_gas_lpm: Optional[float] = Field(default=None, description="MIG shielding gas flow in L/min")
    # Extended process telemetry (optional; populated by mock rig v2)
    reflow_ramp_c_per_s: Optional[float] = Field(default=None, description="Reflow preheat ramp rate (°C/s)")
    reflow_peak_c: Optional[float] = Field(default=None, description="Reflow peak temperature (°C)")
    reflow_tal_s: Optional[float] = Field(default=None, description="Time above liquidus (s)")
    arc_voltage_v: Optional[float] = Field(default=None, description="MIG arc voltage (V)")
    wire_feed_m_per_min: Optional[float] = Field(default=None, description="MIG wire-feed speed (m/min)")


class InspectionRequest(BaseModel):
    """Request payload for `POST /api/inspect`."""

    scenario_key: Optional[str] = Field(default=None)
    line: Optional[Literal["PCB", "CNC", "WELD"]] = Field(default=None)
    sample_id: Optional[str] = Field(default=None)
    custom_image_base64: Optional[str] = Field(
        default=None,
        description="Optional base64-encoded image from live webcam or manual upload",
    )
    sensor_telemetry: Optional[SensorTelemetry] = Field(default=None)
    operator_context: Optional[str] = Field(default=None)
    language: Literal["en-IN", "hi-IN", "mr-IN"] = Field(default="en-IN")


class Tier1TriageResult(BaseModel):
    """Tier-1 combined gate output."""

    pass_status: Literal["HEALTHY", "ESCALATE"]
    anomaly_confidence: float = Field(..., ge=0.0, le=1.0)
    edge_latency_ms: int = Field(..., ge=0)
    escalation_reason: str
    executed_model: str
    short_circuited: bool = Field(default=False)
    t1a_flags: list[str] = Field(default_factory=list)
    t1a_summary: Optional[str] = None
    t1b_vote: Optional[Literal["NOMINAL", "ANOMALY", "UNAVAILABLE", "SKIPPED"]] = None
    t1b_observations: list[str] = Field(default_factory=list)
    t1b_bbox_hint: Optional[list[int]] = None
    provenance_t1a: Optional[StageProvenance] = None
    provenance_t1b: Optional[StageProvenance] = None


class MatchedSOPRecord(BaseModel):
    """Row retrieved from equipment SOP store via embedding cosine similarity or keyword fallback."""

    id: str
    machine_type: str
    fault_code: str
    title: str
    sop_markdown: str
    torque_spec: str
    similarity_score: float = Field(default=0.0)


class Evidence(BaseModel):
    source: Literal["image", "envelope_spectrum", "telemetry", "dsp_features", "sop", "skill"]
    observation: str


class RepairStepChecked(BaseModel):
    text: str
    unverified: bool = False
    unverified_values: list[str] = Field(default_factory=list)


class Tier2DiagnosisResult(BaseModel):
    """Structured diagnosis produced by Tier-2 (or rule-based fallback)."""

    incident_id: str
    defect_type: str = Field(default="OTHER")
    defect_class: str = Field(default="")
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    root_cause_analysis: str
    evidence: list[Evidence] = Field(default_factory=list)
    bbox: Optional[list[int]] = None
    matched_sop_id: str
    skill_applied: str
    recommended_disposition: Literal["RELEASE", "HOLD", "REWORK", "SCRAP"] = "HOLD"
    repair_steps: list[str] = Field(..., min_length=1)
    repair_steps_checked: list[RepairStepChecked] = Field(default_factory=list)
    safety_precautions: list[str] = Field(..., min_length=1)
    safety_precautions_checked: list[RepairStepChecked] = Field(default_factory=list)
    unverified_value_count: int = Field(default=0, ge=0)
    estimated_avoidable_loss_inr: int = Field(default=0, ge=0)
    estimated_downtime_prevented_mins: int = Field(default=0, ge=0)
    economics_basis: str = Field(default="Deterministic calculation from docs/ASSUMPTIONS.md")


class TelemetryMetrics(BaseModel):
    """Stage-by-stage measured latency and provenance telemetry."""

    tier1_ms: int = Field(..., ge=0)
    t1a_ms: int = Field(default=0, ge=0)
    t1b_ms: int = Field(default=0, ge=0)
    retrieval_ms: int = Field(default=0, ge=0)
    tier2_ms: int = Field(default=0, ge=0)
    tier3_ms: int = Field(default=0, ge=0)
    total_ms: int = Field(..., ge=0)
    storage_mode: str
    retrieval_mode: str = "EMBEDDING_COSINE"
    inference_mode: Literal["LIVE_MODEL", "FALLBACK_RULES"]
    tier1_model_used: Optional[str] = None
    tier2_model_used: Optional[str] = None
    tier3_model_used: Optional[str] = None
    total_input_tokens: int = Field(default=0, ge=0)
    total_output_tokens: int = Field(default=0, ge=0)


class InspectionResponse(BaseModel):
    """Complete end-to-end response from `POST /api/inspect`."""

    incident_id: str
    line: str
    scenario_key: str
    sample_id: Optional[str] = None
    line_name: str
    input_simulated: bool = True
    verdict_note: Optional[str] = None
    raw_image_url: str
    audio_url: Optional[str] = None
    envelope_spectrum_data_url: Optional[str] = None
    dsp_features: Optional[dict[str, Any]] = None
    sensor_telemetry: SensorTelemetry
    tier1_triage: Tier1TriageResult
    matched_sops: list[MatchedSOPRecord] = Field(default_factory=list)
    active_skill_metadata: Optional[dict[str, Any]] = None
    tier2_diagnosis: Optional[Tier2DiagnosisResult] = None
    tier3_visual_sop_data_url: Optional[str] = None
    tier3_render_mode: Optional[str] = None
    t3_image: Optional[dict[str, Any]] = None
    provenance: list[StageProvenance] = Field(default_factory=list)
    telemetry: TelemetryMetrics


class DispositionCreate(BaseModel):
    decision: Literal["RELEASE", "HOLD", "REWORK", "SCRAP"]
    role: Literal["QE", "Supervisor"]
    note: str = Field(default="")


class DispositionRecord(BaseModel):
    incident_id: str
    decision: Literal["RELEASE", "HOLD", "REWORK", "SCRAP"]
    role: Literal["QE", "Supervisor"]
    note: str
    recorded_at: str


class ExtractedWorkOrderTags(BaseModel):
    """Structured tags extracted from operator notes."""

    part_code: str
    shift_priority: str
    required_spares: list[str]
    sla_risk: bool = False
    sla_reason: str = ""


class WorkOrderCreate(BaseModel):
    """Payload for `POST /api/work-orders`."""

    incident_id: str
    machine_id: str
    operator_notes: str = Field(..., min_length=3)
    line: Optional[str] = "PCB"
    avoidable_loss_inr: int = Field(default=0, ge=0)


class WorkOrderRecord(BaseModel):
    """Persisted work order record returned from the demo SQLite store."""

    id: str
    incident_id: str
    machine_id: str
    operator_notes: str
    extracted_tags_json: ExtractedWorkOrderTags
    sla_critical_flag: bool
    extraction_producer: str
    extraction_model_id: Optional[str] = None
    status: str = "OPEN"
    avoidable_loss_inr: int = 0
    created_at: str


class CopilotChatRequest(BaseModel):
    """Floor Technician Co-Pilot request grounded in active incident + retrieved SOP."""

    question: str = Field(..., min_length=2)
    line: str = Field(default="PCB")
    scenario_key: Optional[str] = None
    incident_id: Optional[str] = None
    defect_class: Optional[str] = None
    matched_sop_id: Optional[str] = None
    language: Literal["en-IN", "hi-IN", "mr-IN"] = Field(default="en-IN")


class CopilotChatResponse(BaseModel):
    """Response from Tier-4 Co-Pilot."""

    answer: str
    audio_wav_base64: Optional[str] = None
    model_used: Optional[str] = None
    producer: Literal["MODEL", "FALLBACK_MODEL", "FALLBACK_RULES"] = "MODEL"
    grounded_sop_id: str
    latency_ms: int
    unverified_values: list[str] = Field(default_factory=list)
    provenance: Optional[StageProvenance] = None
