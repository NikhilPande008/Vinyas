"""Vinyas — Single-Container FastAPI Backend (`backend/main.py`).

Serves on port 8080:
- `GET /health` & `GET /api/metrics` — Truthful runtime routing & per-model counters
- `GET /api/lines`, `POST /api/rig/draw`, `GET /api/rig/reveal/{sample_id}` — Mock Rig v2 blind mode
- `POST /api/inspect` — T1-A DSP + hedged T1-B visual gate + Embedding Retrieval + Hedged T2 + T3 Overlay
- `POST /api/line-run` — Batch run with measured gated vs cloud-only token accounting
- `POST /api/incidents/{id}/disposition` & `POST /api/work-orders` — Human disposition & work orders
- `WS /api/live-copilot` & `POST /api/copilot/chat` — Tier-4 Floor Co-Pilot (`gemini-3.8-live`)
- Static SPA serving of `/frontend/dist` at `/` with path-traversal protection
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
from backend.db.demo_store import DemoStoreService
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
    DispositionCreate,
    DispositionRecord,
    InspectionRequest,
    InspectionResponse,
    SensorTelemetry,
    StageProvenance,
    TelemetryMetrics,
    WorkOrderCreate,
    WorkOrderRecord,
)
from backend.services.gate import combine_tier1_votes, make_skipped_t1b_provenance
from backend.services.metrics import compute_gate_token_accounting
from backend.services.model_router import GoogleModelRouter
from backend.services.overlay import render_model_bbox_overlay
from backend.services.rate_limiter import TokenBucketRateLimiter
from backend.services.skill_loader import get_skill_loader


demo_store = DemoStoreService()
model_router = GoogleModelRouter()
skill_loader = get_skill_loader()
rate_limiter = TokenBucketRateLimiter(capacity=30, window_seconds=600)

# Tracks sample_ids inspected in this server session so /api/rig/reveal only unlocks post-inspection
_inspected_samples: set[str] = set()
_SAMPLE_ID_RE = re.compile(r"^(PCB|CNC|WELD)-\d{4}$")


class DrawRequest(BaseModel):
    line: str = "PCB"


class LineRunRequest(BaseModel):
    line: str = "CNC"
    n: int = 12


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dataset()
    skill_loader.discover_metadata_only()
    await demo_store.initialize_embeddings(model_router._client)
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
    metrics_snap = model_router.metrics.snapshot()
    routed_models = {
        m
        for m in (
            settings.tier1_visual_gate_model,
            settings.tier1_fallback_model,
            settings.tier1_second_fallback_model,
            settings.tier2_primary_model,
            settings.tier2_fallback_model,
            settings.tier4_live_copilot_model,
            settings.tier4_fallback_model,
            settings.tier4_second_fallback_model,
            settings.wo_extract_model,
        )
        if m
    }
    degraded_models = sorted(
        m
        for m in routed_models
        if m in metrics_snap
        and (metrics_snap[m].get("ok", 0) + metrics_snap[m].get("errors", 0)) >= 5
        and metrics_snap[m].get("ok", 0) == 0
    )
    return {
        "status": "degraded" if degraded_models else "ok",
        "degraded_models": degraded_models,
        "service": "Vinyas — Manufacturing Quality & Predictive Maintenance Platform",
        "cloud_run_ready": True,
        "gcp_project_id": settings.resolved_project_id,
        "region": settings.gcp_location,
        "storage_mode": demo_store.storage_mode,
        "storage_note": "Demo SQLite store — resets when the server restarts",
        "retrieval_mode": demo_store.retrieval_mode,
        "loaded_skills_count": len(skills_status),
        "skills": skills_status,
        "routing_config": model_router.get_routing_config(),
        "model_metrics": metrics_snap,
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
    eval_authorized = (
        settings.eval_reveal_enabled and (eval_mode == 1) and (x_eval_token == settings.eval_token)
    )
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

    # STAGE 1B: Visual/Context Gate (skipped on CNC: bearing is internal and not visible)
    if line == "CNC":
        t1b_vote, t1b_conf, t1b_obs, t1b_bbox = "SKIPPED", 1.0, [], None
        t1b_prov = make_skipped_t1b_provenance(input_simulated=input_simulated)
    else:
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
        await demo_store.log_incident(
            incident_id=incident_id,
            line=line,
            sample_id=sample_id,
            line_name=line_meta["line_name"],
            tier1_status="HEALTHY",
            defect_type="NO_DEFECT_FOUND",
            severity="LOW",
            root_cause=tier1_result.escalation_reason,
            avoidable_loss_inr=0,
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
            storage_mode=demo_store.storage_mode,
            retrieval_mode=demo_store.retrieval_mode,
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

    # STAGE 2: Progressive Skill Activation + Real Embedding SOP Retrieval
    active_skill = skill_loader.activate_skill_for_line(line, t1a_result.all_flags)
    retrieval_query = (
        f"{line} {line_meta['line_name']} flags: {' '.join(t1a_result.all_flags)} "
        f"observations: {' '.join(t1b_obs)}"
    )
    matched_sops, ret_prov = await demo_store.search_sops(
        query_text=retrieval_query,
        genai_client=model_router._client,
        limit=3,
        input_simulated=input_simulated,
    )
    retrieval_ms = ret_prov.latency_ms
    provenance_list.append(ret_prov)

    # STAGE 3: Tier-2 Multimodal Diagnosis (hedged primary/runner-up + SOP guard + deterministic economics)
    diagnosis, t2_prov = await model_router.run_tier2_multimodal_diagnosis(
        line=line,
        sensor_telemetry=sensor_telemetry,
        dsp_features=t1a_result.features,
        t1a_flags=t1a_result.all_flags,
        raw_image_bytes=raw_image_bytes,
        envelope_png_bytes=t1a_result.envelope_png_bytes,
        matched_sops=matched_sops,
        active_skill=active_skill,
        language=request.language,
        input_simulated=input_simulated,
    )
    provenance_list.append(t2_prov)

    # STAGE 4: Tier-3 Deterministic Visual Repair Overlay (model bbox only; never hard-coded)
    matched_sop_obj = next((s for s in matched_sops if s.id == diagnosis.matched_sop_id), None)
    torque_spec = matched_sop_obj.torque_spec if matched_sop_obj else "Verify against matched SOP"
    visual_overlay_url, t3_prov = render_model_bbox_overlay(
        raw_image_bytes=raw_image_bytes,
        diagnosis=diagnosis,
        torque_spec=torque_spec,
        bbox_source_model=t2_prov.model_id or t1b_prov.model_id,
        fallback_bbox_hint=t1b_bbox if line != "CNC" else None,
        input_simulated=input_simulated,
    )
    provenance_list.append(t3_prov)

    total_ms = int((time.perf_counter() - t_start) * 1000)
    in_tok = sum((a.input_tokens or 0) for p in provenance_list for a in p.attempts)
    out_tok = sum((a.output_tokens or 0) for p in provenance_list for a in p.attempts)
    inf_mode = "LIVE_MODEL" if any(p.producer in ("MODEL", "FALLBACK_MODEL") for p in provenance_list) else "FALLBACK_RULES"

    await demo_store.log_incident(
        incident_id=diagnosis.incident_id,
        line=line,
        sample_id=sample_id,
        line_name=line_meta["line_name"],
        tier1_status=tier1_result.pass_status,
        defect_type=diagnosis.defect_type,
        severity=diagnosis.severity,
        root_cause=diagnosis.root_cause_analysis,
        avoidable_loss_inr=diagnosis.estimated_avoidable_loss_inr,
        inference_mode=inf_mode,
        latency_ms=total_ms,
    )

    telemetry = TelemetryMetrics(
        tier1_ms=tier1_result.edge_latency_ms,
        t1a_ms=t1a_result.latency_ms,
        t1b_ms=t1b_prov.latency_ms,
        retrieval_ms=retrieval_ms,
        tier2_ms=t2_prov.latency_ms,
        tier3_ms=t3_prov.latency_ms,
        total_ms=total_ms,
        storage_mode=demo_store.storage_mode,
        retrieval_mode=ret_prov.note or demo_store.retrieval_mode,
        inference_mode=inf_mode,
        tier1_model_used=t1b_prov.model_id,
        tier2_model_used=t2_prov.model_id,
        tier3_model_used=t3_prov.note,
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
            "selection_mode": "deterministic (from line + T1-A flags)",
        },
        tier2_diagnosis=diagnosis,
        tier3_visual_sop_data_url=visual_overlay_url,
        tier3_render_mode=t3_prov.note,
        provenance=provenance_list,
        telemetry=telemetry,
    )


@app.post("/api/line-run")
async def run_batch_line_run(
    req: LineRunRequest,
    http_request: Request,
) -> dict[str, Any]:
    """Run a batch of N random parts through Tier-1 and escalate only flagged parts to Tier-2.

    Measures real gated vs cloud-only token accounting from API usage_metadata.
    """
    rate_limiter.check_request(http_request, cost=10)
    line = req.line.upper()
    if line not in LINE_DEFINITIONS:
        raise HTTPException(status_code=400, detail="Invalid line. Use PCB, CNC, or WELD.")
    n = max(5, min(20, int(req.n)))
    t0 = time.perf_counter()

    parts_log: list[dict[str, Any]] = []
    t1b_tokens_total = 0
    t2_tokens_list: list[int] = []
    escalated_count = 0

    for _ in range(n):
        sample = draw_random_sample(line)
        sid = sample["sample_id"]
        _inspected_samples.add(sid)
        telemetry = SensorTelemetry(**sample["telemetry"])
        wav_path = Path(sample["wav_path"]) if sample.get("wav_path") else None
        raw_img = Path(sample["frame_path"]).read_bytes()
        line_meta = LINE_DEFINITIONS[line]

        t1a = evaluate_t1a_signal_gate(line=line, telemetry=telemetry, wav_path=wav_path)
        if line == "CNC":
            t1b_vote, t1b_conf, t1b_obs, t1b_bbox = "SKIPPED", 1.0, [], None
            t1b_prov = make_skipped_t1b_provenance(input_simulated=True)
        else:
            t1b_vote, t1b_conf, t1b_obs, t1b_bbox, t1b_prov = await model_router.run_tier1_visual_gate(
                line=line,
                line_meta=line_meta,
                t1a_features=t1a.features,
                t1a_flags=t1a.all_flags,
                raw_image_bytes=raw_img,
                input_simulated=True,
            )
        t1_res = combine_tier1_votes(
            t1a=t1a,
            t1b_vote=t1b_vote,
            t1b_confidence=t1b_conf,
            t1b_observations=t1b_obs,
            t1b_bbox_hint=t1b_bbox,
            t1b_provenance=t1b_prov,
            input_simulated=True,
        )
        t1_tok = sum((a.input_tokens or 0) + (a.output_tokens or 0) for a in t1b_prov.attempts)
        t1b_tokens_total += t1_tok

        t2_defect = None
        t2_tok = 0
        if t1_res.pass_status == "ESCALATE":
            escalated_count += 1
            active_skill = skill_loader.activate_skill_for_line(line, t1a.all_flags)
            sops, _ = await demo_store.search_sops(
                query_text=f"{line} {' '.join(t1a.all_flags)} {' '.join(t1b_obs)}",
                genai_client=model_router._client,
                limit=3,
                input_simulated=True,
            )
            diag, t2_prov = await model_router.run_tier2_multimodal_diagnosis(
                line=line,
                sensor_telemetry=telemetry,
                dsp_features=t1a.features,
                t1a_flags=t1a.all_flags,
                raw_image_bytes=raw_img,
                envelope_png_bytes=t1a.envelope_png_bytes,
                matched_sops=sops,
                active_skill=active_skill,
                input_simulated=True,
            )
            t2_defect = diag.defect_type
            t2_tok = sum((a.input_tokens or 0) + (a.output_tokens or 0) for a in t2_prov.attempts)
            t2_tokens_list.append(t2_tok)

        parts_log.append(
            {
                "sample_id": sid,
                "verdict": t1_res.pass_status,
                "t1a_flags": t1a.all_flags,
                "t1b_model": t1b_prov.model_id,
                "t2_defect_type": t2_defect,
                "t1_tokens": t1_tok,
                "t2_tokens": t2_tok,
            }
        )

    token_acc = compute_gate_token_accounting(
        n_parts=n,
        t1_tokens_total=t1b_tokens_total,
        n_escalated=escalated_count,
        t2_success_tokens=[t for t in t2_tokens_list if t > 0],
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "line": line,
        "parts_inspected": n,
        "escalated_count": escalated_count,
        "escalation_rate_pct": round(100.0 * escalated_count / n, 1),
        "gated_tokens": token_acc["gated_tokens"],
        "cloud_only_estimated_tokens": token_acc["cloud_only_tokens"],
        "measured_token_saving_pct": token_acc["saving_pct"],
        "t1_tokens_total": token_acc["t1_tokens_total"],
        "mean_t2_tokens": token_acc["mean_t2_tokens"],
        "t2_calls_failed": token_acc["t2_calls_failed"],
        "token_method": token_acc["method"],
        "note": "Measured from API usage_metadata on simulated mock-rig draws; failed Tier-2 calls are charged the mean measured cost, so outages never count as savings. Real plant savings depend on the plant's defect rate.",
        "elapsed_ms": elapsed_ms,
        "parts": parts_log,
    }


@app.post("/api/incidents/{incident_id}/disposition", response_model=DispositionRecord)
async def record_incident_disposition(
    incident_id: str,
    payload: DispositionCreate,
) -> DispositionRecord:
    """Record a human QE or Supervisor disposition (RELEASE / HOLD / REWORK / SCRAP)."""
    return demo_store.record_disposition(incident_id, payload)


@app.get("/api/incidents/{incident_id}/disposition")
async def get_incident_disposition(incident_id: str) -> dict[str, Any]:
    rec = demo_store.get_disposition(incident_id)
    return {"disposition": rec.model_dump() if rec else None}


@app.post("/api/work-orders", response_model=WorkOrderRecord)
async def create_work_order(payload: WorkOrderCreate) -> WorkOrderRecord:
    """Create a work order (requires prior human HOLD/REWORK/SCRAP disposition)."""
    try:
        return await demo_store.create_work_order(payload, genai_client=model_router._client)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/work-orders")
async def list_work_orders() -> dict[str, Any]:
    """List persisted work orders from the demo SQLite store."""
    orders = await demo_store.list_work_orders(limit=25)
    total_avoidable_loss_inr = sum(o.avoidable_loss_inr for o in orders)
    critical_count = sum(1 for o in orders if o.sla_critical_flag)
    return {
        "storage_mode": demo_store.storage_mode,
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
    """REST fallback endpoint for the Tier-4 Floor Technician Co-Pilot."""
    rate_limiter.check_request(http_request, cost=1)
    matched_sop = demo_store.get_sop_by_id(request.matched_sop_id) if request.matched_sop_id else None
    if matched_sop is None:
        sops, _ = await demo_store.search_sops(
            query_text=f"{request.line} {request.question}",
            genai_client=model_router._client,
            limit=1,
            input_simulated=False,
        )
        matched_sop = sops[0]
    return await model_router.run_tier4_live_copilot(request=request, matched_sop=matched_sop)


@app.websocket("/api/live-copilot")
async def websocket_live_copilot(websocket: WebSocket):
    """Primary WebSocket endpoint for the Tier-4 Floor Technician Co-Pilot (`gemini-3.8-live`)."""
    await websocket.accept()
    try:
        while True:
            raw_msg = await websocket.receive_text()
            try:
                payload = json.loads(raw_msg)
            except Exception:
                payload = {"question": raw_msg, "line": "PCB"}

            lang = payload.get("language", "en-IN")
            if lang not in ("en-IN", "hi-IN", "mr-IN"):
                lang = "en-IN"
            line_val = str(payload.get("line") or "PCB").upper()
            req = CopilotChatRequest(
                question=str(payload.get("question") or "What is the torque spec and repair step?"),
                line=line_val,
                scenario_key=payload.get("scenario_key"),
                incident_id=payload.get("incident_id"),
                defect_class=payload.get("defect_class"),
                matched_sop_id=payload.get("matched_sop_id"),
                language=lang,
            )
            matched_sop = demo_store.get_sop_by_id(req.matched_sop_id) if req.matched_sop_id else None
            if matched_sop is None:
                sops, _ = await demo_store.search_sops(
                    query_text=f"{req.line} {req.question}",
                    genai_client=model_router._client,
                    limit=1,
                    input_simulated=False,
                )
                matched_sop = sops[0]
            resp = await model_router.run_tier4_live_copilot(request=req, matched_sop=matched_sop)
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
