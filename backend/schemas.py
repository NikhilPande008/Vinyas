"""OpsSense AI — Strict Pydantic v2 Data Contracts (`backend/schemas.py`)."""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class SensorTelemetry(BaseModel):
    """Shop-floor machine sensor telemetry associated with an inspection cycle."""

    vibration_khz: float = Field(..., ge=0.0, description="Peak acoustic/vibration frequency in kHz")
    vibration_rms_mms: float = Field(default=1.8, ge=0.0, description="ISO-10816 vibration velocity mm/s RMS")
    temperature_c: float = Field(..., ge=0.0, description="Component or spindle housing temperature in °C")
    line_speed_rpm: int = Field(..., ge=0, description="Spindle RPM or conveyor index speed")
    shielding_gas_lpm: Optional[float] = Field(default=None, description="MIG shielding gas flow in L/min")


class InspectionRequest(BaseModel):
    """Request payload for `POST /api/inspect`."""

    scenario_key: Literal[
        "LINE_A_PCB",
        "LINE_B_CNC",
        "LINE_C_WELD",
        "LINE_D_HEALTHY",
    ] = Field(default="LINE_A_PCB")
    custom_image_base64: Optional[str] = Field(
        default=None,
        description="Optional base64-encoded image from live webcam or manual upload override",
    )
    sensor_telemetry: Optional[SensorTelemetry] = Field(default=None)
    operator_context: Optional[str] = Field(default=None)


class Tier1TriageResult(BaseModel):
    """Tier-1 Edge Anomaly Gate output (`Gemma 4 E4B` / `gemini-3.5-flash-lite` emulator)."""

    pass_status: Literal["HEALTHY", "ESCALATE"]
    anomaly_confidence: float = Field(..., ge=0.0, le=1.0)
    edge_latency_ms: int = Field(..., ge=1)
    escalation_reason: str
    executed_model: str = Field(default="gemini-3.5-flash-lite (Gemma 4 E4B Cloud Edge Emulator)")
    short_circuited: bool = Field(default=False)
    cloud_tokens_saved_pct: float = Field(default=0.0)


class MatchedSOPRecord(BaseModel):
    """Row retrieved from AlloyDB Express `equipment_sops` via ScaNN cosine similarity."""

    id: str
    machine_type: str
    fault_code: str
    title: str
    sop_markdown: str
    torque_spec: str
    similarity_score: float = Field(default=0.94)


class Tier2DiagnosisResult(BaseModel):
    """Strict JSON schema for Tier-2 Multimodal Root-Cause & ScaNN RAG Engine (`gemini-4-hydrogen`)."""

    incident_id: str
    defect_class: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    root_cause_analysis: str
    matched_sop_id: str
    skill_applied: str
    repair_steps: list[str] = Field(..., min_length=1)
    estimated_scrap_saved_inr: int = Field(..., ge=0)
    estimated_downtime_prevented_mins: int = Field(..., ge=0)
    safety_precautions: list[str] = Field(..., min_length=1)


class TelemetryMetrics(BaseModel):
    """Stage-by-stage latency and architecture provenance telemetry."""

    tier1_ms: int = Field(..., ge=0)
    scann_rag_ms: int = Field(default=0, ge=0)
    tier2_ms: int = Field(default=0, ge=0)
    tier3_ms: int = Field(default=0, ge=0)
    total_ms: int = Field(..., ge=0)
    storage_mode: Literal["ALLOYDB_EXPRESS_SCANN", "LOCAL_SQLITE_FALLBACK"]
    db_ai_mode: Literal["ALLOYDB_IN_SQL", "PYTHON_FALLBACK"]
    inference_mode: Literal["LIVE_GOOGLE_AI", "CACHED_FALLBACK"]
    tier1_model_used: str
    tier2_model_used: Optional[str] = None
    tier3_model_used: Optional[str] = None


class InspectionResponse(BaseModel):
    """Complete end-to-end response from `POST /api/inspect`."""

    scenario_key: str
    line_name: str
    raw_image_url: str
    audio_url: Optional[str] = None
    sensor_telemetry: SensorTelemetry
    tier1_triage: Tier1TriageResult
    matched_sops: list[MatchedSOPRecord] = Field(default_factory=list)
    active_skill_metadata: Optional[dict[str, Any]] = None
    tier2_diagnosis: Optional[Tier2DiagnosisResult] = None
    tier3_visual_sop_data_url: Optional[str] = None
    tier3_render_mode: Optional[str] = None
    telemetry: TelemetryMetrics


class ExtractedWorkOrderTags(BaseModel):
    """Structured tags extracted inside PostgreSQL 18 via `AI.EXTRACT()`."""

    part_code: str
    shift_priority: str
    required_spares: list[str]


class WorkOrderCreate(BaseModel):
    """Payload for `POST /api/work-orders`."""

    incident_id: str
    machine_id: str
    operator_notes: str = Field(..., min_length=3)
    scenario_key: Optional[str] = "LINE_A_PCB"
    scrap_saved_inr: int = Field(default=34600, ge=0)


class WorkOrderRecord(BaseModel):
    """Persisted work order record returned from AlloyDB Express / SQLite fallback."""

    id: str
    incident_id: str
    machine_id: str
    operator_notes: str
    extracted_tags_json: ExtractedWorkOrderTags
    sla_critical_flag: bool
    db_ai_mode: Literal["ALLOYDB_IN_SQL", "PYTHON_FALLBACK"]
    status: str = "OPEN"
    scrap_saved_inr: int = 0
    created_at: str


class CopilotChatRequest(BaseModel):
    """Floor Technician Co-Pilot request grounded in active incident + ScaNN SOP."""

    question: str = Field(..., min_length=2)
    scenario_key: str = Field(default="LINE_A_PCB")
    incident_id: Optional[str] = None
    defect_class: Optional[str] = None
    matched_sop_id: Optional[str] = None


class CopilotChatResponse(BaseModel):
    """Response from `gemini-3.8-live` / streaming co-pilot."""

    answer: str
    model_used: str
    inference_mode: Literal["LIVE_GOOGLE_AI", "CACHED_FALLBACK"]
    grounded_sop_id: str
    latency_ms: int
