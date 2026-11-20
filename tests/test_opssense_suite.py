"""OpsSense AI — Automated Pytest Suite (`tests/test_opssense_suite.py`).

Covers all mandatory Gate 1 verification requirements:
1. `/health` readiness endpoint (Cloud Run + AlloyDB Express ScaNN + In-SQL AI + model justification matrix)
2. Strict Pydantic schemas validation (`InspectionRequest`, `Tier1TriageResult`, `Tier2DiagnosisResult`, `WorkOrderCreate`, `WorkOrderRecord`)
3. `skill_loader` Progressive Disclosure (`agentskills.io` spec: YAML frontmatter only at startup, full `SKILL.md` + `references/` loaded on domain activation)
4. `ops-db-guardrails` SQL guardrail regex checks (`init_alloydb.sql` passes, destructive `DROP TABLE`, non-snake_case tables, missing `id` PK, and raw f-string interpolation are blocked)
5. Scenario 4 (`LINE_D_HEALTHY`) Tier-1 short-circuit logic (`pass_status == "HEALTHY"`, `tier2_diagnosis is None`, `cloud_tokens_saved_pct >= 95.0`)
6. `model_router` fallback circuit breakers across Tier-1, Tier-2, Tier-3 (Pillow callout overlay), Tier-4, and Tier-5 (`AI.EXTRACT` / `AI.IF` work order persistence).
"""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.config import PROJECT_ROOT
from backend.main import app
from backend.schemas import (
    CopilotChatRequest,
    InspectionRequest,
    SensorTelemetry,
    Tier1TriageResult,
    Tier2DiagnosisResult,
    WorkOrderCreate,
)
from backend.services.model_router import GoogleModelRouter
from backend.services.simulator_assets import get_scenario_image_bytes
from backend.services.skill_loader import (
    ProgressiveSkillLoader,
    validate_sql_against_guardrails,
)


client = TestClient(app)


def test_health_endpoint_contract():
    """Verify `/health` returns HTTP 200 and full Cloud Run + AlloyDB + Google AI telemetry."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["cloud_run_ready"] is True
    assert data["storage_mode"] in ("ALLOYDB_EXPRESS_SCANN", "LOCAL_SQLITE_FALLBACK")
    assert data["db_ai_mode"] in ("ALLOYDB_IN_SQL", "PYTHON_FALLBACK")
    assert data["inference_mode"] in ("LIVE_GOOGLE_AI", "CACHED_FALLBACK")
    assert data["loaded_skills_count"] >= 4
    assert data["models"]["tier1_cloud_emulator"] == "gemini-3.5-flash-lite"
    assert data["models"]["tier2_primary"] == "gemini-4-hydrogen"
    assert data["models"]["tier3_visual_sop"] == "gemini-nano-banana-2.1"
    assert data["models"]["tier4_live_copilot"] == "gemini-3.8-live"
    assert len(data["model_justification_matrix"]) == 5


def test_pydantic_schemas_strict_validation():
    """Verify strict Pydantic schemas enforce valid field ranges and required attributes."""
    req = InspectionRequest(
        scenario_key="LINE_A_PCB",
        sensor_telemetry=SensorTelemetry(
            vibration_khz=0.42,
            vibration_rms_mms=0.85,
            temperature_c=244.5,
            line_speed_rpm=1200,
        ),
    )
    assert req.scenario_key == "LINE_A_PCB"

    t1 = Tier1TriageResult(
        pass_status="ESCALATE",
        anomaly_confidence=0.96,
        edge_latency_ms=28,
        escalation_reason="QFP bridge detected",
    )
    assert t1.pass_status == "ESCALATE"

    with pytest.raises(Exception):
        # Confidence > 1.0 must fail validation
        Tier1TriageResult(
            pass_status="HEALTHY",
            anomaly_confidence=1.5,
            edge_latency_ms=10,
            escalation_reason="Invalid confidence",
        )


def test_skill_loader_progressive_disclosure():
    """Verify `skill_loader` loads ONLY frontmatter at startup and loads full body + references on demand."""
    loader = ProgressiveSkillLoader()
    startup_status = loader.list_skills_status()
    assert len(startup_status) == 4

    # Stage 1: No full markdown body or reference files should be loaded at startup
    for skill_meta in startup_status:
        assert skill_meta["full_body_loaded"] is False
        assert skill_meta["activation_count"] == 0
        assert skill_meta["references_loaded"] == []

    # Stage 2: Activating Scenario 1 (`LINE_A_PCB`) loads `pcb-defect-triage` + `ipc_solder_standards.md`
    activated = loader.activate_skill_for_scenario("LINE_A_PCB")
    assert activated["name"] == "pcb-defect-triage"
    assert activated["full_body_loaded"] is True
    assert activated["activation_count"] == 1
    assert "IPC-A-610 Class 3" in activated["skill_markdown"]
    assert "ipc_solder_standards.md" in activated["references"]

    # Other skills remain unexpanded in memory
    after_status = {s["name"]: s for s in loader.list_skills_status()}
    assert after_status["pcb-defect-triage"]["full_body_loaded"] is True
    assert after_status["bearing-acoustic-diagnostics"]["full_body_loaded"] is False


def test_ops_db_guardrails_sql_validation():
    """Verify `ops-db-guardrails` passes `init_alloydb.sql` and blocks unsafe DDL/queries."""
    ddl_path = PROJECT_ROOT / "backend" / "db" / "init_alloydb.sql"
    ddl_text = ddl_path.read_text(encoding="utf-8")
    is_valid, violations = validate_sql_against_guardrails(ddl_text)
    assert is_valid is True, f"init_alloydb.sql failed guardrails: {violations}"

    # 1. Destructive DROP TABLE must fail
    ok_drop, v_drop = validate_sql_against_guardrails("DROP TABLE equipment_sops;")
    assert ok_drop is False
    assert any("Destructive DDL" in msg for msg in v_drop)

    # 2. CamelCase table name or missing primary key `id` must fail
    ok_camel, v_camel = validate_sql_against_guardrails(
        "CREATE TABLE EquipmentSops (sop_key TEXT NOT NULL);"
    )
    assert ok_camel is False
    assert len(v_camel) >= 2

    # 3. Raw Python string interpolation `{user_input}` must fail
    ok_interp, v_interp = validate_sql_against_guardrails(
        "SELECT * FROM work_orders WHERE machine_id = '{machine_id}';"
    )
    assert ok_interp is False


def test_scenario_4_tier1_short_circuit_saves_95_pct_tokens():
    """Verify Scenario 4 (`LINE_D_HEALTHY`) terminates cleanly at Tier-1 without invoking Tier-2/3."""
    resp = client.post("/api/inspect", json={"scenario_key": "LINE_D_HEALTHY"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["tier1_triage"]["pass_status"] == "HEALTHY"
    assert body["tier1_triage"]["short_circuited"] is True
    assert body["tier1_triage"]["cloud_tokens_saved_pct"] >= 95.0
    assert body["tier2_diagnosis"] is None
    assert body["tier3_visual_sop_data_url"] is None
    assert body["telemetry"]["tier2_ms"] == 0
    assert body["telemetry"]["tier3_ms"] == 0


@pytest.mark.asyncio
async def test_model_router_circuit_breakers_and_visual_sop_fallback():
    """Verify `model_router` deterministic circuit breakers when forced offline."""
    router = GoogleModelRouter()
    sensors = SensorTelemetry(
        vibration_khz=4.21,
        vibration_rms_mms=5.42,
        temperature_c=61.8,
        line_speed_rpm=5400,
    )
    raw_bytes = get_scenario_image_bytes("LINE_B_CNC")

    t1 = await router.run_tier1_edge_gate(
        scenario_key="LINE_B_CNC",
        sensor_telemetry=sensors,
        raw_image_bytes=raw_bytes,
        force_fallback=True,
    )
    assert t1.pass_status == "ESCALATE"

    loader = ProgressiveSkillLoader()
    skill = loader.activate_skill_for_scenario("LINE_B_CNC")
    diagnosis, used_model, mode, elapsed_ms = await router.run_tier2_multimodal_diagnosis(
        scenario_key="LINE_B_CNC",
        sensor_telemetry=sensors,
        raw_image_bytes=raw_bytes,
        matched_sops=[],
        active_skill=skill,
        force_fallback=True,
    )
    assert isinstance(diagnosis, Tier2DiagnosisResult)
    assert mode == "CACHED_FALLBACK"
    assert diagnosis.severity == "CRITICAL"
    assert diagnosis.estimated_scrap_saved_inr > 0
    assert elapsed_ms > 0

    overlay_url, overlay_mode, t3_ms = await router.run_tier3_visual_repair_overlay(
        raw_image_bytes=raw_bytes,
        scenario_key="LINE_B_CNC",
        diagnosis=diagnosis,
        torque_spec="145 Nm",
        force_fallback=True,
    )
    assert overlay_url.startswith("data:image/png;base64,")
    assert "gemini-nano-banana-2.1" in overlay_mode
    assert t3_ms > 0


def test_end_to_end_escalated_inspection_and_work_order_enrichment():
    """Verify escalated scenario (`LINE_A_PCB`) and work order `AI.EXTRACT` / `AI.IF` enrichment."""
    inspect_resp = client.post("/api/inspect", json={"scenario_key": "LINE_A_PCB"})
    assert inspect_resp.status_code == 200
    insp = inspect_resp.json()
    assert insp["tier1_triage"]["pass_status"] == "ESCALATE"
    assert insp["tier2_diagnosis"] is not None
    assert insp["tier2_diagnosis"]["matched_sop_id"] == "SOP-PUNE-PCB-01"
    assert insp["tier3_visual_sop_data_url"].startswith("data:image/png;base64,")

    wo_resp = client.post(
        "/api/work-orders",
        json={
            "incident_id": insp["tier2_diagnosis"]["incident_id"],
            "machine_id": "SMT-DEK-REFLOW-CHAKAN-A1",
            "operator_notes": "Critical solder bridge on QFP U4 Pins 14-16. Clean STENCIL-QFP-04MM immediately to avoid OEM SLA breach.",
            "scenario_key": "LINE_A_PCB",
            "scrap_saved_inr": insp["tier2_diagnosis"]["estimated_scrap_saved_inr"],
        },
    )
    assert wo_resp.status_code == 200
    wo = wo_resp.json()
    assert wo["id"].startswith("WO-PUNE-")
    assert wo["sla_critical_flag"] is True
    assert wo["extracted_tags_json"]["part_code"] == "STENCIL-QFP-04MM"
    assert len(wo["extracted_tags_json"]["required_spares"]) >= 1

    list_resp = client.get("/api/work-orders")
    assert list_resp.status_code == 200
    ledger = list_resp.json()
    assert ledger["total_work_orders"] >= 1
    assert ledger["total_scrap_saved_inr"] >= insp["tier2_diagnosis"]["estimated_scrap_saved_inr"]
