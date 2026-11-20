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
import re
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import PROJECT_ROOT, get_settings
from backend.db.alloydb_service import AlloyDBService
from backend.dsp.envelope import evaluate_t1a_signal_gate
from backend.mock_rig.dataset import (
    LINE_DEFINITIONS,
    MANIFEST_PATH,
    SAMPLES_DIR,
    draw_random_sample,
    ensure_dataset,
    load_sample_public,
)
from backend.schemas import (
    CopilotChatRequest,
    CopilotChatResponse,
    InspectionRequest,
    InspectionResponse,
    SensorTelemetry,
    StageProvenance,
    TelemetryMetrics,
    WorkOrderCreate,
    WorkOrderRecord,
)
from backend.services.gate import combine_tier1_votes
from backend.services.model_router import GoogleModelRouter
from backend.services.rate_limiter import TokenBucketRateLimiter
from backend.services.skill_loader import get_skill_loader


alloydb_service = AlloyDBService()
model_router = GoogleModelRouter()
skill_loader = get_skill_loader()
rate_limiter = TokenBucketRateLimiter(capacity=30, window_seconds=600)

# Tracks sample_ids inspected in this server session so /api/rig/reveal only unlocks post-inspection
_inspected_samples: set[str] = set()
_SAMPLE_ID_RE = re.compile(r"^(PCB|CNC|WELD)-\d{4}$")


class DrawRequest(BaseModel):
    line: str = "PCB"


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dataset()
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


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health & readiness endpoint with truthful runtime counters and routing config."""
    settings = get_settings()
    skills_status = skill_loader.list_skills_status()
    return {
        "status": "ok",
        "service": "Vinyas — Manufacturing Quality & Predictive Maintenance Platform",
        "cloud_run_ready": True,
        "gcp_project_id": settings.resolved_project_id,
        "region": settings.gcp_location,
        "storage_mode": alloydb_service.storage_mode,
        "storage_note": "Demo SQLite store — resets when the server restarts",
        "loaded_skills_count": len(skills_status),
        "skills": skills_status,
        "routing_config": model_router.get_routing_config(),
        "model_metrics": model_router.metrics.snapshot(),
    }


@app.get("/api/metrics")
async def get_runtime_metrics() -> dict[str, Any]:
    """Return per-model call counters and measured p50 latencies since startup."""
    return {
        "routing_config": model_router.get_routing_config(),
        "models": model_router.metrics.snapshot(),
    }


@app.get("/api/lines")
async def list_lines() -> dict[str, Any]:
    """Return the three simulated production lines with machine metadata (no verdicts)."""
    ensure_dataset()
    return {"lines": list(LINE_DEFINITIONS.values())}


@app.post("/api/rig/draw")
async def draw_part(req: DrawRequest) -> dict[str, Any]:
    """Draw a random simulated part for a line. Never returns ground-truth labels."""
    line = req.line.upper()
    if line not in LINE_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Unknown line '{req.line}'. Use PCB, CNC, or WELD.")
    sample = draw_random_sample(line)
    sid = sample["sample_id"]
    return {
        "sample_id": sid,
        "line": line,
        "machine_id": sample["machine_id"],
        "part_sku": sample["part_sku"],
        "frame_url": f"/api/rig/sample/{sid}/frame.png",
        "wav_url": f"/api/rig/sample/{sid}/vib.wav" if sample["has_wav"] else None,
        "telemetry": sample["telemetry"],
        "input_simulated": True,
    }


@app.get("/api/rig/sample/{sample_id}/{filename}")
async def serve_rig_sample_file(sample_id: str, filename: str):
    """Serve allow-listed simulated sample files (`frame.png` or `vib.wav`)."""
    if not _SAMPLE_ID_RE.match(sample_id):
        raise HTTPException(status_code=404, detail="Sample not found")
    if filename not in {"frame.png", "vib.wav"}:
        raise HTTPException(status_code=404, detail="File not found")
    ensure_dataset()
    samples_root = SAMPLES_DIR.resolve()
    target = (samples_root / sample_id / filename).resolve()
    if not target.is_relative_to(samples_root) or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = "audio/wav" if filename.endswith(".wav") else "image/png"
    return FileResponse(target, media_type=media_type)


@app.get("/api/rig/reveal/{sample_id}")
async def reveal_ground_truth(
    sample_id: str,
    eval_mode: int = Query(default=0, alias="eval"),
    x_eval_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Reveal ground-truth label ONLY after the sample was inspected (or with eval token)."""
    if not _SAMPLE_ID_RE.match(sample_id):
        raise HTTPException(status_code=404, detail="Sample not found")
    settings = get_settings()
    eval_authorized = (eval_mode == 1) and (x_eval_token == settings.eval_token)
    if sample_id not in _inspected_samples and not eval_authorized:
        raise HTTPException(
            status_code=403,
            detail="Inspect this sample first before revealing ground truth.",
        )
    if not MANIFEST_PATH.is_file():
        raise HTTPException(status_code=404, detail="Manifest not found")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for entry in manifest:
        if entry["sample_id"] == sample_id:
            return entry
    raise HTTPException(status_code=404, detail="Sample not found in manifest")


@app.get("/api/skills")
async def list_skills() -> dict[str, Any]:
    """Return progressive disclosure status for `.agents/skills/`."""
    return {
        "progressive_disclosure_spec": "agentskills.io",
        "skills": skill_loader.list_skills_status(),
    }


@app.get("/api/assets/{filename}")
async def serve_legacy_asset(filename: str):
    """Legacy asset endpoint disabled; use /api/rig/sample/{sample_id}/{filename}."""
    raise HTTPException(status_code=404, detail="Asset not found")


def _default_nominal_telemetry(line: str) -> SensorTelemetry:
    if line == "CNC":
        return SensorTelemetry(vibration_khz=0.09, vibration_rms_mms=0.9, temperature_c=41.0, line_speed_rpm=5400)
    if line == "WELD":
        return SensorTelemetry(
            vibration_khz=0.8,
            vibration_rms_mms=1.3,
            temperature_c=270.0,
            line_speed_rpm=1850,
            shielding_gas_lpm=17.0,
            arc_voltage_v=22.0,
            wire_feed_m_per_min=8.5,
        )
    return SensorTelemetry(
        vibration_khz=0.35,
        vibration_rms_mms=0.7,
        temperature_c=242.0,
        line_speed_rpm=1200,
        reflow_ramp_c_per_s=2.0,
        reflow_peak_c=242.0,
        reflow_tal_s=65.0,
    )


@app.post("/api/inspect", response_model=InspectionResponse)
async def run_edge_to_cloud_inspection(
    request: InspectionRequest,
    http_request: Request,
) -> InspectionResponse:
    """Execute the inspection pipeline on a drawn mock-rig sample or uploaded image."""
    rate_limiter.check_request(http_request, cost=1)
    t_start = time.perf_counter()

    # Resolve line and sample inputs WITHOUT ever reading manifest.json
    sample_id = request.sample_id
    wav_path: Path | None = None
    verdict_note: str | None = None

    if request.custom_image_base64:
        line = (request.line or "PCB").upper()
        if line not in LINE_DEFINITIONS:
            line = "PCB"
        input_simulated = False
        b64_clean = request.custom_image_base64.split(",")[-1]
        try:
            raw_image_bytes = base64.b64decode(b64_clean)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid base64 image") from exc
        raw_image_url = (
            request.custom_image_base64
            if request.custom_image_base64.startswith("data:")
            else f"data:image/png;base64,{b64_clean}"
        )
        sensor_telemetry = request.sensor_telemetry or _default_nominal_telemetry(line)
        audio_url = None
        verdict_note = "Uploaded image: verdict is driven by the visual gate (plus user-selected telemetry)."
    else:
        if sample_id:
            if not _SAMPLE_ID_RE.match(sample_id):
                raise HTTPException(status_code=400, detail="Invalid sample_id format")
            try:
                sample = load_sample_public(sample_id)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        else:
            line_hint = (request.line or "PCB").upper()
            if line_hint not in LINE_DEFINITIONS:
                line_hint = "PCB"
            sample = draw_random_sample(line_hint)
            sample_id = sample["sample_id"]
        line = sample["line"]
        input_simulated = True
        raw_image_bytes = Path(sample["frame_path"]).read_bytes()
        raw_image_url = f"/api/rig/sample/{sample_id}/frame.png"
        audio_url = f"/api/rig/sample/{sample_id}/vib.wav" if sample["has_wav"] else None
        wav_path = Path(sample["wav_path"]) if sample.get("wav_path") else None
        sensor_telemetry = request.sensor_telemetry or SensorTelemetry(**sample["telemetry"])
        _inspected_samples.add(sample_id)

    line_meta = LINE_DEFINITIONS[line]
    scenario_key = f"LINE_{line}"

    # STAGE 1A: Deterministic DSP & Process-Window Gate
    t1a_result = evaluate_t1a_signal_gate(
        line=line,
        telemetry=sensor_telemetry,
        wav_path=wav_path,
    )

    # STAGE 1B: Visual/Context Gate (Gemma 4 26B-A4B -> gemini-3.1-flash-lite)
    t1b_vote, t1b_conf, t1b_obs, t1b_bbox, t1b_prov = await model_router.run_tier1_visual_gate(
        line=line,
        line_meta=line_meta,
        t1a_features=t1a_result.features,
        t1a_flags=t1a_result.all_flags,
        raw_image_bytes=raw_image_bytes,
        input_simulated=input_simulated,
    )

    # Combine T1-A and T1-B votes (fail-safe)
    tier1_result = combine_tier1_votes(
        t1a=t1a_result,
        t1b_vote=t1b_vote,
        t1b_confidence=t1b_conf,
        t1b_observations=t1b_obs,
        t1b_bbox_hint=t1b_bbox,
        t1b_provenance=t1b_prov,
        input_simulated=input_simulated,
    )

    provenance_list: list[StageProvenance] = []
    if tier1_result.provenance_t1a:
        provenance_list.append(tier1_result.provenance_t1a)
    if tier1_result.provenance_t1b:
        provenance_list.append(tier1_result.provenance_t1b)

    if tier1_result.pass_status == "HEALTHY":
        incident_id = f"INC-PASS-{int(time.time()) % 100000}"
        total_ms = int((time.perf_counter() - t_start) * 1000)
        in_tok = sum((a.input_tokens or 0) for p in provenance_list for a in p.attempts)
        out_tok = sum((a.output_tokens or 0) for p in provenance_list for a in p.attempts)
        inf_mode = "LIVE_MODEL" if any(p.producer in ("MODEL", "FALLBACK_MODEL") for p in provenance_list) else "FALLBACK_RULES"
        await alloydb_service.log_incident(
            incident_id=incident_id,
            scenario_key=scenario_key,
            line_name=line_meta["line_name"],
            tier1_status="HEALTHY",
            defect_class="NONE",
            severity="LOW",
            root_cause=tier1_result.escalation_reason,
            scrap_saved_inr=0,
            inference_mode=inf_mode,
            latency_ms=total_ms,
        )
        telemetry = TelemetryMetrics(
            tier1_ms=tier1_result.edge_latency_ms,
            t1a_ms=t1a_result.latency_ms,
            t1b_ms=t1b_prov.latency_ms,
            retrieval_ms=0,
            tier2_ms=0,
            tier3_ms=0,
            total_ms=total_ms,
            storage_mode=alloydb_service.storage_mode,
            inference_mode=inf_mode,
            tier1_model_used=t1b_prov.model_id,
            tier2_model_used=None,
            tier3_model_used=None,
            total_input_tokens=in_tok,
            total_output_tokens=out_tok,
        )
        return InspectionResponse(
            incident_id=incident_id,
            line=line,
            scenario_key=scenario_key,
            sample_id=sample_id,
            line_name=line_meta["line_name"],
            input_simulated=input_simulated,
            verdict_note=verdict_note,
            raw_image_url=raw_image_url,
            audio_url=audio_url,
            envelope_spectrum_data_url=t1a_result.envelope_data_url,
            dsp_features=t1a_result.features,
            sensor_telemetry=sensor_telemetry,
            tier1_triage=tier1_result,
            matched_sops=[],
            active_skill_metadata={"name": "none", "full_body_loaded": False},
            tier2_diagnosis=None,
            tier3_visual_sop_data_url=None,
            tier3_render_mode=None,
            provenance=provenance_list,
            telemetry=telemetry,
        )

    # STAGE 2: Skill Activation + SOP Retrieval
    active_skill = skill_loader.activate_skill_for_scenario(scenario_key)
    matched_sops, retrieval_ms = await alloydb_service.search_sops_scann(
        query_text=f"{line_meta['line_name']} {tier1_result.escalation_reason}",
        scenario_key=scenario_key,
        limit=3,
    )
    provenance_list.append(
        StageProvenance(
            stage="RETRIEVAL",
            producer="DETERMINISTIC",
            model_id=None,
            latency_ms=retrieval_ms,
            input_simulated=input_simulated,
        )
    )

    # STAGE 3: Tier-2 Multimodal Diagnosis
    diagnosis, t2_prov = await model_router.run_tier2_multimodal_diagnosis(
        scenario_key=scenario_key,
        sensor_telemetry=sensor_telemetry,
        raw_image_bytes=raw_image_bytes,
        matched_sops=matched_sops,
        active_skill=active_skill,
        input_simulated=input_simulated,
    )
    provenance_list.append(t2_prov)

    total_ms = int((time.perf_counter() - t_start) * 1000)
    in_tok = sum((a.input_tokens or 0) for p in provenance_list for a in p.attempts)
    out_tok = sum((a.output_tokens or 0) for p in provenance_list for a in p.attempts)
    inf_mode = "LIVE_MODEL" if any(p.producer in ("MODEL", "FALLBACK_MODEL") for p in provenance_list) else "FALLBACK_RULES"

    await alloydb_service.log_incident(
        incident_id=diagnosis.incident_id,
        scenario_key=scenario_key,
        line_name=line_meta["line_name"],
        tier1_status=tier1_result.pass_status,
        defect_class=diagnosis.defect_class or diagnosis.defect_type,
        severity=diagnosis.severity,
        root_cause=diagnosis.root_cause_analysis,
        scrap_saved_inr=diagnosis.estimated_avoidable_loss_inr,
        inference_mode=inf_mode,
        latency_ms=total_ms,
    )

    telemetry = TelemetryMetrics(
        tier1_ms=tier1_result.edge_latency_ms,
        t1a_ms=t1a_result.latency_ms,
        t1b_ms=t1b_prov.latency_ms,
        retrieval_ms=retrieval_ms,
        tier2_ms=t2_prov.latency_ms,
        tier3_ms=0,
        total_ms=total_ms,
        storage_mode=alloydb_service.storage_mode,
        inference_mode=inf_mode,
        tier1_model_used=t1b_prov.model_id,
        tier2_model_used=t2_prov.model_id,
        tier3_model_used=None,
        total_input_tokens=in_tok,
        total_output_tokens=out_tok,
    )

    return InspectionResponse(
        incident_id=diagnosis.incident_id,
        line=line,
        scenario_key=scenario_key,
        sample_id=sample_id,
        line_name=line_meta["line_name"],
        input_simulated=input_simulated,
        verdict_note=verdict_note,
        raw_image_url=raw_image_url,
        audio_url=audio_url,
        envelope_spectrum_data_url=t1a_result.envelope_data_url,
        dsp_features=t1a_result.features,
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
        tier3_visual_sop_data_url=None,
        tier3_render_mode="PENDING_PHASE_4",
        provenance=provenance_list,
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
    total_avoidable_loss_inr = sum(o.avoidable_loss_inr for o in orders)
    critical_count = sum(1 for o in orders if o.sla_critical_flag)
    return {
        "storage_mode": alloydb_service.storage_mode,
        "storage_note": "Demo store — resets when the server restarts",
        "total_work_orders": len(orders),
        "critical_sla_count": critical_count,
        "total_avoidable_loss_inr": total_avoidable_loss_inr,
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
