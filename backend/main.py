"""Vinyas — Single-Container FastAPI Backend (`backend/main.py`).

Serves on port 8080:
- `GET /health` — Cloud Run + AlloyDB Express ScaNN + In-SQL AI + Google AI readiness
- `GET /api/scenarios` — 4 Virtual Factory Line Simulator scenarios
- `GET /api/skills` — `.agents/skills/` Progressive Disclosure status
- `GET /api/assets/{filename}` — High-contrast inspection PNGs & 48 kHz WAV audio
- `POST /api/inspect` — Full 5-stage Edge-to-Cloud inspection pipeline (with Scenario 4 Tier-1 short-circuit)
- `GET /api/work-orders` & `POST /api/work-orders` — AlloyDB `AI.EXTRACT()` & `AI.IF()` work order ledger
- `POST /api/copilot/chat` & `WS /api/live-copilot` — Tier-4 Hands-Free Floor Technician Co-Pilot (`gemini-3.8-live`)
- Static SPA serving of `/frontend/dist` at `/` for zero-CORS single-container Cloud Run deployment
"""

from __future__ import annotations

import base64
from contextlib import asynccontextmanager
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import PROJECT_ROOT, get_settings
from backend.db.alloydb_service import AlloyDBService
from backend.schemas import (
    CopilotChatRequest,
    CopilotChatResponse,
    InspectionRequest,
    InspectionResponse,
    SensorTelemetry,
    TelemetryMetrics,
    WorkOrderCreate,
    WorkOrderRecord,
)
from backend.services.model_router import GoogleModelRouter
from backend.services.rate_limiter import TokenBucketRateLimiter
from backend.services.simulator_assets import (
    ASSETS_DIR,
    SCENARIO_DEFINITIONS,
    ensure_simulator_assets,
    get_scenario_image_bytes,
    get_scenarios_list,
)
from backend.services.skill_loader import get_skill_loader


alloydb_service = AlloyDBService()
model_router = GoogleModelRouter()
skill_loader = get_skill_loader()
rate_limiter = TokenBucketRateLimiter(capacity=30, window_seconds=600)


def _allowed_asset_filenames() -> set[str]:
    allowed: set[str] = set()
    for meta in SCENARIO_DEFINITIONS.values():
        if meta.get("image_filename"):
            allowed.add(Path(str(meta["image_filename"])).name)
        if meta.get("audio_filename"):
            allowed.add(Path(str(meta["audio_filename"])).name)
    return allowed


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_simulator_assets()
    skill_loader.discover_metadata_only()
    await alloydb_service.initialize()
    yield


app = FastAPI(
    title="Vinyas — Manufacturing Quality & Predictive Maintenance Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# SPA is served same-origin on Cloud Run; allow only explicit local Vite dev origins without credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Eval-Token"],
)


MODEL_JUSTIFICATION_MATRIX: list[dict[str, str]] = [
    {
        "tier": "Tier 1: Edge Anomaly Gate",
        "model": "Gemma 4 E4B (Edge) / gemini-3.5-flash-lite (Cloud Sandbox Emulator)",
        "why": "Streaming 24/7 factory camera & 48 kHz acoustic feeds to frontier cloud models destroys unit economics and exposes plant IP.",
        "exact_use": "Pre-screens every part in <50 ms. Short-circuits Scenario 4 (Healthy Baseline Part) at Tier-1, saving ~95.4% of Tier-2 cloud token spend.",
    },
    {
        "tier": "Tier 2: Multimodal Root-Cause & ScaNN RAG",
        "model": "gemini-4-hydrogen (Primary) / gemini-3.8-flash (Fallback)",
        "why": "Complex cross-modal defects require joint reasoning across optical images, vibration harmonics, AlloyDB ScaNN SOPs, and progressive SKILL.md rules.",
        "exact_use": "Executes ONLY on ESCALATE. Returns strict Pydantic JSON with root cause, matched AlloyDB SOP ID, ordered repair steps, and INR scrap saved.",
    },
    {
        "tier": "Tier 3: Visual Repair SOP Overlay",
        "model": "gemini-nano-banana-2.1 (Primary) / Pillow Precision Callout Renderer (Fallback)",
        "why": "Shop-floor operators act 3x faster on visual callout cards overlaid directly onto the defect frame than on dense text manuals.",
        "exact_use": "Generates an annotated visual repair overlay card with fault bounding boxes, torque specifications, and SynthID provenance.",
    },
    {
        "tier": "Tier 4: Hands-Free Floor Technician Co-Pilot",
        "model": "gemini-3.8-live (Primary WebSocket) / gemini-3.8-flash (Streaming Fallback)",
        "why": "Technicians wearing PPE gloves while inspecting CNC spindles or weld cells cannot type long troubleshooting queries.",
        "exact_use": "Powers `/api/live-copilot` WebSocket & quick-chip voice assistant grounded in the active incident diagnosis and AlloyDB ScaNN SOP.",
    },
    {
        "tier": "Tier 5: In-Database Work Order Enrichment",
        "model": "AlloyDB Express (PostgreSQL 18) ScaNN + AI.EXTRACT() & AI.IF()",
        "why": "Eliminates fragile external ETL pipelines when logging maintenance tickets from raw operator floor notes.",
        "exact_use": "Performs sub-10ms ScaNN cosine vector retrieval on `equipment_sops` and runs `ai.extract()` / `ai.if()` to tag spare part SKUs & OEM SLA risk.",
    },
]


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health & readiness endpoint required by Cloud Run and Top Telemetry Bar."""
    settings = get_settings()
    skills_status = skill_loader.list_skills_status()
    return {
        "status": "ok",
        "service": "Vinyas — Manufacturing Quality & Predictive Maintenance Platform",
        "cloud_run_ready": True,
        "gcp_project_id": settings.resolved_project_id,
        "region": settings.gcp_location,
        "storage_mode": alloydb_service.storage_mode,
        "db_ai_mode": alloydb_service.db_ai_mode,
        "inference_mode": model_router.last_inference_mode,
        "loaded_skills_count": len(skills_status),
        "skills": skills_status,
        "models": {
            "tier1_physical_edge": settings.tier1_edge_physical_model,
            "tier1_cloud_emulator": settings.tier1_cloud_emulator_model,
            "tier2_primary": settings.tier2_primary_model,
            "tier2_fallback": settings.tier2_fallback_model,
            "tier3_visual_sop": settings.tier3_visual_sop_model,
            "tier4_live_copilot": settings.tier4_live_copilot_model,
            "tier5_db_ai": "AlloyDB Express PostgreSQL 18 ScaNN + AI.EXTRACT() + AI.IF()",
        },
        "model_justification_matrix": MODEL_JUSTIFICATION_MATRIX,
    }


@app.get("/api/scenarios")
async def list_scenarios() -> dict[str, Any]:
    """Return the 4 Virtual Factory Line Simulator scenarios."""
    return {"scenarios": get_scenarios_list()}


@app.get("/api/skills")
async def list_skills() -> dict[str, Any]:
    """Return progressive disclosure status for `.agents/skills/`."""
    return {
        "progressive_disclosure_spec": "agentskills.io",
        "skills": skill_loader.list_skills_status(),
    }


@app.get("/api/assets/{filename}")
async def serve_simulator_asset(filename: str):
    """Serve allow-listed simulator PNGs and WAV audio."""
    ensure_simulator_assets()
    decoded = unquote(filename)
    if ".." in decoded or "/" in decoded or "\\" in decoded:
        raise HTTPException(status_code=404, detail="Asset not found")
    safe_name = Path(decoded).name
    if safe_name not in _allowed_asset_filenames():
        raise HTTPException(status_code=404, detail="Asset not found")
    assets_root = ASSETS_DIR.resolve()
    target = (assets_root / safe_name).resolve()
    if not target.is_relative_to(assets_root) or not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    media_type = "audio/wav" if safe_name.endswith(".wav") else "image/png"
    return FileResponse(target, media_type=media_type)


@app.post("/api/inspect", response_model=InspectionResponse)
async def run_edge_to_cloud_inspection(
    request: InspectionRequest,
    http_request: Request,
) -> InspectionResponse:
    """Execute the 5-stage Edge-to-Cloud inspection pipeline."""
    rate_limiter.check_request(http_request, cost=1)
    t_start = time.perf_counter()
    scenario_meta = SCENARIO_DEFINITIONS.get(request.scenario_key, SCENARIO_DEFINITIONS["LINE_A_PCB"])

    sensor_telemetry = request.sensor_telemetry or SensorTelemetry(
        **scenario_meta["sensor_telemetry"]
    )

    if request.custom_image_base64:
        b64_clean = request.custom_image_base64.split(",")[-1]
        try:
            raw_image_bytes = base64.b64decode(b64_clean)
            raw_image_url = (
                request.custom_image_base64
                if request.custom_image_base64.startswith("data:")
                else f"data:image/png;base64,{b64_clean}"
            )
        except Exception:
            raw_image_bytes = get_scenario_image_bytes(request.scenario_key)
            raw_image_url = f"/api/assets/{scenario_meta['image_filename']}"
    else:
        raw_image_bytes = get_scenario_image_bytes(request.scenario_key)
        raw_image_url = f"/api/assets/{scenario_meta['image_filename']}"

    audio_url = (
        f"/api/assets/{scenario_meta['audio_filename']}"
        if scenario_meta.get("audio_filename")
        else None
    )

    # STAGE 1: Tier-1 Edge Anomaly Gate (Gemma 4 E4B / gemini-3.5-flash-lite Cloud Emulator)
    tier1_result = await model_router.run_tier1_edge_gate(
        scenario_key=request.scenario_key,
        sensor_telemetry=sensor_telemetry,
        raw_image_bytes=raw_image_bytes,
    )

    # MANDATORY SHORT-CIRCUIT RULE FOR SCENARIO 4 (HEALTHY BASELINE PART)
    if tier1_result.pass_status == "HEALTHY":
        total_ms = max(tier1_result.edge_latency_ms, int((time.perf_counter() - t_start) * 1000))
        await alloydb_service.log_incident(
            incident_id=f"INC-HEALTHY-{int(time.time()) % 10000}",
            scenario_key=request.scenario_key,
            line_name=scenario_meta["line_name"],
            tier1_status="HEALTHY",
            defect_class="NONE (NOMINAL BASELINE PASS)",
            severity="LOW",
            root_cause=tier1_result.escalation_reason,
            scrap_saved_inr=0,
            inference_mode=model_router.last_inference_mode,
            latency_ms=total_ms,
        )
        telemetry = TelemetryMetrics(
            tier1_ms=tier1_result.edge_latency_ms,
            scann_rag_ms=0,
            tier2_ms=0,
            tier3_ms=0,
            total_ms=total_ms,
            storage_mode=alloydb_service.storage_mode,
            db_ai_mode=alloydb_service.db_ai_mode,
            inference_mode=model_router.last_inference_mode,
            tier1_model_used=tier1_result.executed_model,
            tier2_model_used="SHORT_CIRCUITED_AT_EDGE (0 Tokens)",
            tier3_model_used="SHORT_CIRCUITED_AT_EDGE (0 Tokens)",
        )
        return InspectionResponse(
            scenario_key=request.scenario_key,
            line_name=scenario_meta["line_name"],
            raw_image_url=raw_image_url,
            audio_url=audio_url,
            sensor_telemetry=sensor_telemetry,
            tier1_triage=tier1_result,
            matched_sops=[],
            active_skill_metadata={
                "name": "none (short-circuited at Tier-1)",
                "full_body_loaded": False,
                "tokens_saved_pct": 95.4,
            },
            tier2_diagnosis=None,
            tier3_visual_sop_data_url=None,
            tier3_render_mode="SHORT_CIRCUITED_HEALTHY",
            telemetry=telemetry,
        )

    # STAGE 2: Progressive Skill Activation + AlloyDB Express ScaNN Vector Retrieval
    active_skill = skill_loader.activate_skill_for_scenario(request.scenario_key)
    matched_sops, scann_ms = await alloydb_service.search_sops_scann(
        query_text=f"{scenario_meta['subtitle']} {tier1_result.escalation_reason}",
        scenario_key=request.scenario_key,
        limit=3,
    )

    # STAGE 3: Tier-2 Multimodal Root-Cause & ScaNN RAG Diagnosis (gemini-4-hydrogen -> gemini-3.8-flash)
    diagnosis, tier2_model_used, inference_mode, tier2_ms = (
        await model_router.run_tier2_multimodal_diagnosis(
            scenario_key=request.scenario_key,
            sensor_telemetry=sensor_telemetry,
            raw_image_bytes=raw_image_bytes,
            matched_sops=matched_sops,
            active_skill=active_skill,
        )
    )

    # STAGE 4: Tier-3 Visual Repair SOP Overlay (gemini-nano-banana-2.1 -> Pillow fallback)
    primary_torque = matched_sops[0].torque_spec if matched_sops else "Standard Calibrated Torque"
    visual_overlay_url, tier3_model_used, tier3_ms = (
        await model_router.run_tier3_visual_repair_overlay(
            raw_image_bytes=raw_image_bytes,
            scenario_key=request.scenario_key,
            diagnosis=diagnosis,
            torque_spec=primary_torque,
        )
    )

    total_ms = max(
        tier1_result.edge_latency_ms + scann_ms + tier2_ms + tier3_ms,
        int((time.perf_counter() - t_start) * 1000),
    )

    await alloydb_service.log_incident(
        incident_id=diagnosis.incident_id,
        scenario_key=request.scenario_key,
        line_name=scenario_meta["line_name"],
        tier1_status=tier1_result.pass_status,
        defect_class=diagnosis.defect_class,
        severity=diagnosis.severity,
        root_cause=diagnosis.root_cause_analysis,
        scrap_saved_inr=diagnosis.estimated_scrap_saved_inr,
        inference_mode=inference_mode,
        latency_ms=total_ms,
    )

    telemetry = TelemetryMetrics(
        tier1_ms=tier1_result.edge_latency_ms,
        scann_rag_ms=scann_ms,
        tier2_ms=tier2_ms,
        tier3_ms=tier3_ms,
        total_ms=total_ms,
        storage_mode=alloydb_service.storage_mode,
        db_ai_mode=alloydb_service.db_ai_mode,
        inference_mode=inference_mode,
        tier1_model_used=tier1_result.executed_model,
        tier2_model_used=tier2_model_used,
        tier3_model_used=tier3_model_used,
    )

    return InspectionResponse(
        scenario_key=request.scenario_key,
        line_name=scenario_meta["line_name"],
        raw_image_url=raw_image_url,
        audio_url=audio_url,
        sensor_telemetry=sensor_telemetry,
        tier1_triage=tier1_result,
        matched_sops=matched_sops,
        active_skill_metadata={
            "name": active_skill["name"],
            "description": active_skill["description"],
            "full_body_loaded": active_skill["full_body_loaded"],
            "activation_count": active_skill["activation_count"],
            "references_loaded": list(active_skill["references"].keys()),
        },
        tier2_diagnosis=diagnosis,
        tier3_visual_sop_data_url=visual_overlay_url,
        tier3_render_mode=tier3_model_used,
        telemetry=telemetry,
    )


@app.post("/api/work-orders", response_model=WorkOrderRecord)
async def create_work_order(payload: WorkOrderCreate) -> WorkOrderRecord:
    """Create and enrich a work order using AlloyDB `AI.EXTRACT()` and `AI.IF()`."""
    return await alloydb_service.create_work_order(payload)


@app.get("/api/work-orders")
async def list_work_orders() -> dict[str, Any]:
    """List persisted work orders and cumulative plant INR savings."""
    orders = await alloydb_service.list_work_orders(limit=25)
    total_scrap_saved_inr = sum(o.scrap_saved_inr for o in orders)
    critical_count = sum(1 for o in orders if o.sla_critical_flag)
    return {
        "storage_mode": alloydb_service.storage_mode,
        "db_ai_mode": alloydb_service.db_ai_mode,
        "total_work_orders": len(orders),
        "critical_sla_count": critical_count,
        "total_scrap_saved_inr": total_scrap_saved_inr,
        "work_orders": [o.model_dump() for o in orders],
    }


@app.post("/api/copilot/chat", response_model=CopilotChatResponse)
async def copilot_chat(
    request: CopilotChatRequest,
    http_request: Request,
) -> CopilotChatResponse:
    """REST endpoint for the Tier-4 Hands-Free Floor Technician Co-Pilot."""
    rate_limiter.check_request(http_request, cost=1)
    sops, _ = await alloydb_service.search_sops_scann(
        query_text=f"{request.scenario_key} {request.question}",
        scenario_key=request.scenario_key,
        limit=1,
    )
    matched_sop = sops[0]
    return await model_router.run_tier4_live_copilot(request=request, matched_sop=matched_sop)


@app.websocket("/api/live-copilot")
async def websocket_live_copilot(websocket: WebSocket):
    """WebSocket streaming endpoint backed by `gemini-3.8-live` with automatic flash fallback."""
    await websocket.accept()
    try:
        while True:
            raw_msg = await websocket.receive_text()
            try:
                payload = json.loads(raw_msg)
            except Exception:
                payload = {"question": raw_msg, "scenario_key": "LINE_A_PCB"}

            req = CopilotChatRequest(
                question=str(payload.get("question") or "What is the torque spec and repair step?"),
                scenario_key=str(payload.get("scenario_key") or "LINE_A_PCB"),
                incident_id=payload.get("incident_id"),
                defect_class=payload.get("defect_class"),
                matched_sop_id=payload.get("matched_sop_id"),
            )
            sops, _ = await alloydb_service.search_sops_scann(
                query_text=f"{req.scenario_key} {req.question}",
                scenario_key=req.scenario_key,
                limit=1,
            )
            resp = await model_router.run_tier4_live_copilot(request=req, matched_sop=sops[0])
            await websocket.send_json(resp.model_dump())
    except WebSocketDisconnect:
        return


FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend_assets")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve static files strictly inside `/frontend/dist` or fall back to `index.html`."""
    decoded = unquote(unquote(full_path))
    if ".." in decoded or "\\" in decoded or decoded.startswith("/"):
        raise HTTPException(status_code=404, detail="Not found")

    if decoded.startswith("api/") or decoded == "api" or decoded == "health":
        raise HTTPException(status_code=404, detail="API route not found")

    if FRONTEND_DIST.exists():
        dist_root = FRONTEND_DIST.resolve()
        if decoded:
            candidate = (dist_root / decoded).resolve()
            if candidate.is_relative_to(dist_root) and candidate.is_file():
                return FileResponse(candidate)
        index_html = dist_root / "index.html"
        if index_html.is_file():
            return FileResponse(index_html)

    return JSONResponse(
        {
            "service": "Vinyas — Manufacturing Quality & Predictive Maintenance Platform",
            "status": "online",
            "docs_url": "/docs",
            "health_url": "/health",
        }
    )
