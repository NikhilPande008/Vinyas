"""Vinyas — SQLite Demo Store, Gemini Embedding Retrieval, Dispositions & Work Orders (`backend/db/demo_store.py`).

Storage note: Demo SQLite store — resets when the Cloud Run container restarts.
Production PostgreSQL/AlloyDB schema lives in `infra/alloydb_schema.sql` (not deployed).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.schemas import (
    DispositionCreate,
    DispositionRecord,
    ExtractedWorkOrderTags,
    MatchedSOPRecord,
    StageProvenance,
    WorkOrderCreate,
    WorkOrderRecord,
)

try:
    from google.genai import types as genai_types
except ImportError:
    genai_types = None  # type: ignore


# 18 realistic SOPs across PCB, CNC, and WELD lines including distractors (zero real OEM names)
SEED_SOPS: list[dict[str, Any]] = [
    # --- PCB SMT LINE (6 SOPs) ---
    {
        "id": "SOP-PCB-01",
        "machine_type": "SMT_REFLOW_PCB",
        "fault_code": "IPC610-SOLDER-BRIDGE",
        "title": "Fine-Pitch QFP Solder Bridge & Stencil Paste Slump Remediation (IPC-A-610 Class 3)",
        "sop_markdown": (
            "1. Quarantine PCB panel on ESD rework station. "
            "2. Apply ROL0 no-clean flux across bridged QFP leads and wick excess SAC305 solder using 1.0 mm copper braid at 330°C. "
            "3. Verify >0.15 mm inter-lead clearance under 20x stereo microscope. "
            "4. Run stencil underside vacuum wipe and set reflow preheat ramp within 1.0-3.0 °C/s (target 1.8 °C/s)."
        ),
        "torque_spec": "Squeegee Blade Clamp: 4.5 Nm | Stencil Frame Lock: 1.2 Nm",
    },
    {
        "id": "SOP-PCB-02",
        "machine_type": "SMT_REFLOW_PCB",
        "fault_code": "IPC610-INSUFFICIENT-SOLDER",
        "title": "QFP Insufficient Solder Fillet & Cold Joint Reflow Recovery (IPC-A-610 Class 3)",
        "sop_markdown": (
            "1. Hold panel and inspect starved QFP pads under 20x magnification. "
            "2. Check stencil aperture blockage and solder paste viscosity; verify SAC305 reflow peak 235-250°C and Time Above Liquidus 45-90 s. "
            "3. Touch up starved leads with 0.3 mm SAC305 wire at 330°C using ROL0 flux and re-verify wetting."
        ),
        "torque_spec": "Squeegee Blade Clamp: 4.5 Nm",
    },
    {
        "id": "SOP-PCB-03",
        "machine_type": "SMT_REFLOW_PCB",
        "fault_code": "IPC610-FLUX-RESIDUE-COSMETIC",
        "title": "No-Clean Flux Residue Glare Verification (Cosmetic Hard-Negative Check)",
        "sop_markdown": (
            "1. Confirm translucent glossy residue sits on solder mask without conductive bridging across leads. "
            "2. Verify >0.15 mm lead clearance under 20x microscope; if intact, QE may release part without rework."
        ),
        "torque_spec": "No mechanical adjustment required",
    },
    {
        "id": "SOP-PCB-04",
        "machine_type": "SMT_REFLOW_PCB",
        "fault_code": "IPC7095-BGA-VOID",
        "title": "Automotive ECU Power BGA Thermal Pad Voiding & Nitrogen Reflow Check",
        "sop_markdown": (
            "1. Inspect 2D X-ray void area (>25% reject threshold per IPC-7095 Class 3). "
            "2. Verify nitrogen reflow atmosphere <800 ppm O2 and extend 165°C soak by 15 s."
        ),
        "torque_spec": "Conveyor Rail Lock: 6.0 Nm",
    },
    {
        "id": "SOP-PCB-05",
        "machine_type": "SMT_REFLOW_PCB",
        "fault_code": "IPC610-TOMBSTONING",
        "title": "0402 Passive Chip Tombstoning & Pick-and-Place Nozzle Offset Calibration",
        "sop_markdown": (
            "1. Check pick-and-place nozzle Z-axis height and vacuum pressure (0.08 MPa). "
            "2. Balance reflow Zone 2-3 ramp rate to 1.5 °C/s to prevent differential pad wetting."
        ),
        "torque_spec": "Feeder Clamp Bolt: 2.5 Nm",
    },
    {
        "id": "SOP-PCB-06",
        "machine_type": "SMT_REFLOW_PCB",
        "fault_code": "SMT-CONVEYOR-JAM",
        "title": "SMT Reflow Conveyor Rail Width Drift & Board Jam Recovery",
        "sop_markdown": (
            "1. Pause upstream loader and allow oven zones to cool safely. "
            "2. Check rail parallelism within 0.2 mm and re-home width actuator."
        ),
        "torque_spec": "Conveyor Rail Lock: 6.0 Nm",
    },
    # --- CNC SPINDLE LINE (6 SOPs) ---
    {
        "id": "SOP-CNC-01",
        "machine_type": "CNC_SPINDLE",
        "fault_code": "ISO20816-BPFO-OUTER-RACE",
        "title": "CNC Spindle Angular-Contact Bearing Outer-Race Fault & Cartridge Replacement",
        "sop_markdown": (
            "1. Execute M01 controlled feed-hold at end of current pass and engage spindle lock. "
            "2. Confirm periodic BPFO envelope harmonic (~793 Hz at 5400 rpm, exciting ~4.2 kHz structural resonance) and spindle temperature >55°C. "
            "3. Replace front duplex 7014C P4 angular-contact bearing set (SKU: SP-7014C-P4S) and flush air-oil mist lines at 0.35 MPa. "
            "4. Verify spindle taper dynamic runout <0.003 mm TIR before resuming production."
        ),
        "torque_spec": "Spindle Bearing Locknut: 145 Nm | Drawbar Retention Stud: 85 Nm",
    },
    {
        "id": "SOP-CNC-02",
        "machine_type": "CNC_SPINDLE",
        "fault_code": "ISO20816-IMBALANCE-1X",
        "title": "CNC Spindle & Toolholder 1x Shaft Harmonic Imbalance Remediation",
        "sop_markdown": (
            "1. Stop spindle and inspect toolholder taper for chip ingress or eccentric wear. "
            "2. Check 1x shaft harmonic (~90 Hz at 5400 rpm) and ISO 20816-3 Group 2 velocity zone (C >= 2.8 mm/s, D >= 4.5 mm/s). "
            "3. Re-balance toolholder assembly to G2.5 at 5400 rpm and verify runout <0.005 mm."
        ),
        "torque_spec": "Toolholder Pull-Stud: 75 Nm",
    },
    {
        "id": "SOP-CNC-03",
        "machine_type": "CNC_SPINDLE",
        "fault_code": "CNC-TRANSIENT-IMPACT-CHECK",
        "title": "Single Non-Periodic Transient Impact Verification (Wrench Strike / Fixture Knock)",
        "sop_markdown": (
            "1. Verify high bandpass kurtosis occurred without periodic BPFO/BPFI envelope harmonics. "
            "2. Inspect fixture clamps for loose hardware; if RMS velocity stays in Zone A (<1.4 mm/s), log and resume."
        ),
        "torque_spec": "Fixture Clamp Bolt: 40 Nm",
    },
    {
        "id": "SOP-CNC-04",
        "machine_type": "CNC_SPINDLE",
        "fault_code": "CNC-REGENERATIVE-CHATTER",
        "title": "Finish Boring Bar Regenerative Tool Chatter Suppression & Insert Indexing",
        "sop_markdown": (
            "1. Reduce spindle RPM by 12% to exit regenerative stability lobe and adjust feedrate +5%. "
            "2. Index CNMG-120408 TiAlN carbide insert to a fresh cutting edge."
        ),
        "torque_spec": "Insert Torx Screw (M4): 3.8 Nm | Toolholder Pull-Stud: 75 Nm",
    },
    {
        "id": "SOP-CNC-05",
        "machine_type": "CNC_SPINDLE",
        "fault_code": "ISO20816-BPFI-INNER-RACE",
        "title": "CNC Spindle Bearing Inner-Race Pitting & Lubrication Starvation Check",
        "sop_markdown": (
            "1. Confirm periodic BPFI envelope peak (~1007 Hz at 5400 rpm) with 1x shaft sidebands. "
            "2. Inspect air-oil mist supply pressure (0.35 MPa) and schedule cartridge overhaul."
        ),
        "torque_spec": "Spindle Bearing Locknut: 145 Nm",
    },
    {
        "id": "SOP-CNC-06",
        "machine_type": "CNC_SPINDLE",
        "fault_code": "CNC-DRAWBAR-CLAMP-LOSS",
        "title": "CNC Spindle Drawbar Clamping Force Drop & Belleville Stack Inspection",
        "sop_markdown": (
            "1. Measure drawbar pull force with calibrated gauge (nominal 12 kN). "
            "2. Replace fatigued Belleville disc spring stack and verify taper seating."
        ),
        "torque_spec": "Drawbar Retention Stud: 85 Nm",
    },
    # --- MIG WELD LINE (6 SOPs) ---
    {
        "id": "SOP-WELD-01",
        "machine_type": "MIG_CHASSIS_WELD",
        "fault_code": "MIG-POROSITY-GAS-LOSS",
        "title": "Robotic MIG Chassis Subframe Seam Porosity & Shielding Gas Restoration",
        "sop_markdown": (
            "1. Interlock robotic weld cell after current fixture unclamp. "
            "2. Grind out porous weld bead to sound base metal using a zirconia flap disc. "
            "3. Replace spatter-clogged 16 mm conical gas nozzle (SKU: NOZ-MIG-16MM) and 1.2 mm CuCrZr contact tip. "
            "4. Restore 82% Ar / 18% CO2 shielding gas flow to 15-20 L/min (target 16.5 L/min) and re-weld per OEM WPS."
        ),
        "torque_spec": "MIG Torch Swan-Neck Nut: 22 Nm | Gas Regulator Nut: 18 Nm",
    },
    {
        "id": "SOP-WELD-02",
        "machine_type": "MIG_CHASSIS_WELD",
        "fault_code": "MIG-SPATTER-COSMETIC",
        "title": "MIG Plate Cosmetic Spatter Verification (Sound Seam Check)",
        "sop_markdown": (
            "1. Confirm weld bead shows uniform ripple with zero surface pinholes and gas flow within 15-20 L/min. "
            "2. Chip cosmetic spatter droplets beside the bead if required by drawing; QE may release without re-weld."
        ),
        "torque_spec": "No torch adjustment required",
    },
    {
        "id": "SOP-WELD-03",
        "machine_type": "MIG_CHASSIS_WELD",
        "fault_code": "MIG-CONTACT-TIP-WEAR",
        "title": "MIG Contact Tip Keyhole Wear & Arc Voltage Drift Remediation",
        "sop_markdown": (
            "1. Check arc voltage stability (nominal 20-24 V) and wire-feed speed (7.5-9.5 m/min). "
            "2. Replace worn 1.2 mm CuCrZr contact tip and blow out liner with dry compressed air at 0.4 MPa."
        ),
        "torque_spec": "MIG Torch Swan-Neck Nut: 22 Nm",
    },
    {
        "id": "SOP-WELD-04",
        "machine_type": "MIG_CHASSIS_WELD",
        "fault_code": "MIG-WIRE-FEED-SLIP",
        "title": "MIG Wire-Feed Drive Roll Slip & Liner Friction Check",
        "sop_markdown": (
            "1. Inspect V-groove drive rolls for copper shaving buildup and verify tension setting. "
            "2. Confirm steady wire feed 7.5-9.5 m/min before resuming weld cycle."
        ),
        "torque_spec": "Drive Roll Retaining Bolt: 8.0 Nm",
    },
    {
        "id": "SOP-WELD-05",
        "machine_type": "MIG_CHASSIS_WELD",
        "fault_code": "MIG-WELD-UNDERCUT",
        "title": "Robotic MIG Fillet Weld Toe Undercut & Travel Speed Correction",
        "sop_markdown": (
            "1. Measure undercut depth (<0.5 mm limit for demo D1.1-style criteria; follow OEM weld spec). "
            "2. Reduce robot travel speed by 10% and verify arc voltage 20-24 V."
        ),
        "torque_spec": "Torch Mount Clamp: 16 Nm",
    },
    {
        "id": "SOP-WELD-06",
        "machine_type": "MIG_CHASSIS_WELD",
        "fault_code": "WELD-FIXTURE-CLAMP-FAULT",
        "title": "Robotic Weld Cell Pneumatic Fixture Clamp Interlock Recovery",
        "sop_markdown": (
            "1. Verify cell light-curtain interlock is engaged before entering envelope. "
            "2. Check pneumatic clamp supply pressure (0.6 MPa) and reed switch alignment."
        ),
        "torque_spec": "Fixture Locator Pin Nut: 35 Nm",
    },
]



def _as_separate_contents(texts: list[str]) -> list[Any]:
    """Wrap each text as its own Content so the API returns one embedding per text."""
    if genai_types is None:
        return list(texts)
    return [genai_types.Content(parts=[genai_types.Part(text=t)]) for t in texts]


def _log_retrieval_event(event: str, detail: str) -> None:
    print(json.dumps({"event": event, "stage": "RETRIEVAL", "detail": detail}), flush=True)


class _WOExtractionSchema(BaseModel):
    part_code: str = Field(..., description="Spare part or component SKU if mentioned, else inferred standard SKU")
    shift_priority: str = Field(..., description="P1_IMMEDIATE, P2_CURRENT_SHIFT, or P3_PLANNED_PM")
    required_spares: list[str] = Field(..., min_length=1)
    sla_risk: bool
    sla_reason: str


def _content_hash(sop: dict[str, Any]) -> str:
    payload = f"{sop['id']}|{sop['machine_type']}|{sop['fault_code']}|{sop['title']}|{sop['sop_markdown']}|{sop['torque_spec']}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _sop_embed_text(sop: dict[str, Any]) -> str:
    return f"{sop['id']} {sop['machine_type']} {sop['fault_code']} {sop['title']}. {sop['sop_markdown']} Spec: {sop['torque_spec']}"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return max(0.0, min(1.0, dot / (na * nb)))


def _keyword_score(query: str, sop: dict[str, Any]) -> float:
    q_tokens = set(re.findall(r"[a-z0-9_]+", query.lower()))
    s_tokens = set(re.findall(r"[a-z0-9_]+", _sop_embed_text(sop).lower()))
    if not q_tokens or not s_tokens:
        return 0.0
    overlap = len(q_tokens & s_tokens)
    return round(min(1.0, overlap / max(1.0, math.sqrt(len(q_tokens) * len(s_tokens)) * 0.6)), 3)


class DemoStoreService:
    """SQLite demo store with real `gemini-embedding-2` retrieval, dispositions, and work orders."""

    def __init__(self, sqlite_path: Optional[str] = None) -> None:
        settings = get_settings()
        self.settings = settings
        self.sqlite_path = sqlite_path or settings.sqlite_db_path
        self.storage_mode = "DEMO_SQLITE"
        self.retrieval_mode = "KEYWORD_FALLBACK"
        self._sop_vectors: dict[str, list[float]] = {}
        self._init_sqlite()

    def _init_sqlite(self) -> None:
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.sqlite_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS equipment_sops (
                    id TEXT PRIMARY KEY,
                    machine_type TEXT NOT NULL,
                    fault_code TEXT NOT NULL,
                    title TEXT NOT NULL,
                    sop_markdown TEXT NOT NULL,
                    torque_spec TEXT NOT NULL,
                    content_hash TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sop_embeddings (
                    sop_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    PRIMARY KEY (sop_id, model_id, content_hash)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS inspection_incidents (
                    id TEXT PRIMARY KEY,
                    line TEXT NOT NULL,
                    sample_id TEXT,
                    line_name TEXT NOT NULL,
                    tier1_status TEXT NOT NULL,
                    defect_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    root_cause TEXT NOT NULL,
                    avoidable_loss_inr INTEGER NOT NULL DEFAULT 0,
                    inference_mode TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS incident_dispositions (
                    incident_id TEXT PRIMARY KEY,
                    decision TEXT NOT NULL,
                    role TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    recorded_at TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS work_orders (
                    id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    operator_notes TEXT NOT NULL,
                    extracted_tags_json TEXT NOT NULL,
                    sla_critical_flag INTEGER NOT NULL DEFAULT 0,
                    extraction_producer TEXT NOT NULL DEFAULT 'FALLBACK_RULES',
                    extraction_model_id TEXT,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    avoidable_loss_inr INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )

            for sop in SEED_SOPS:
                cur.execute(
                    """
                    INSERT OR REPLACE INTO equipment_sops
                    (id, machine_type, fault_code, title, sop_markdown, torque_spec, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sop["id"],
                        sop["machine_type"],
                        sop["fault_code"],
                        sop["title"],
                        sop["sop_markdown"],
                        sop["torque_spec"],
                        _content_hash(sop),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    async def initialize_embeddings(self, genai_client: Any) -> None:
        """Load cached `gemini-embedding-2` vectors from SQLite and batch-embed any missing SOPs."""
        model_id = self.settings.embedding_model
        dim = self.settings.embedding_dim

        conn = sqlite3.connect(self.sqlite_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT sop_id, content_hash, embedding_json FROM sop_embeddings WHERE model_id = ?",
                (model_id,),
            )
            cached = {(row[0], row[1]): json.loads(row[2]) for row in cur.fetchall()}
        finally:
            conn.close()

        missing: list[dict[str, Any]] = []
        for sop in SEED_SOPS:
            h = _content_hash(sop)
            if (sop["id"], h) in cached:
                self._sop_vectors[sop["id"]] = cached[(sop["id"], h)]
            else:
                missing.append(sop)

        if missing and genai_client is not None and genai_types is not None:
            try:
                texts = [_sop_embed_text(s) for s in missing]
                resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        genai_client.models.embed_content,
                        model=model_id,
                        # One Content per SOP: newer SDKs merge a plain list of strings into ONE embedding.
                        contents=_as_separate_contents(texts),
                        config=genai_types.EmbedContentConfig(output_dimensionality=dim),
                    ),
                    timeout=12.0,
                )
                if resp and getattr(resp, "embeddings", None) and len(resp.embeddings) == len(missing):
                    conn = sqlite3.connect(self.sqlite_path)
                    try:
                        cur = conn.cursor()
                        for sop, emb_obj in zip(missing, resp.embeddings):
                            vec = [float(v) for v in emb_obj.values]
                            self._sop_vectors[sop["id"]] = vec
                            cur.execute(
                                """
                                INSERT OR REPLACE INTO sop_embeddings
                                (sop_id, model_id, content_hash, embedding_json)
                                VALUES (?, ?, ?, ?)
                                """,
                                (sop["id"], model_id, _content_hash(sop), json.dumps(vec)),
                            )
                        conn.commit()
                    finally:
                        conn.close()
                else:
                    _log_retrieval_event("sop_embedding_count_mismatch", f"expected {len(missing)}, got {len(getattr(resp, 'embeddings', None) or [])}")
            except Exception as exc:  # noqa: BLE001 - logged, keyword fallback is labelled
                _log_retrieval_event("sop_embedding_error", f"{type(exc).__name__}: {str(exc)[:120]}")

        if len(self._sop_vectors) == len(SEED_SOPS):
            self.retrieval_mode = f"EMBEDDING_COSINE ({model_id})"
        else:
            self.retrieval_mode = "KEYWORD_FALLBACK"

    async def search_sops(
        self,
        query_text: str,
        genai_client: Any = None,
        limit: int = 3,
        input_simulated: bool = True,
    ) -> tuple[list[MatchedSOPRecord], StageProvenance]:
        """Rank all 18 SOPs by real `gemini-embedding-2` cosine similarity (or labelled keyword fallback)."""
        t0 = time.perf_counter()
        model_id = self.settings.embedding_model
        dim = self.settings.embedding_dim

        # Ensure embeddings are populated if client is available
        if len(self._sop_vectors) < len(SEED_SOPS) and genai_client is not None:
            await self.initialize_embeddings(genai_client)

        if (
            len(self._sop_vectors) == len(SEED_SOPS)
            and genai_client is not None
            and genai_types is not None
        ):
            try:
                resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        genai_client.models.embed_content,
                        model=model_id,
                        contents=_as_separate_contents([query_text]),
                        config=genai_types.EmbedContentConfig(output_dimensionality=dim),
                    ),
                    timeout=5.0,
                )
                if resp and getattr(resp, "embeddings", None):
                    q_vec = [float(v) for v in resp.embeddings[0].values]
                    scored = []
                    for sop in SEED_SOPS:
                        sim = round(_cosine(q_vec, self._sop_vectors[sop["id"]]), 3)
                        scored.append(
                            (
                                sim,
                                MatchedSOPRecord(
                                    id=sop["id"],
                                    machine_type=sop["machine_type"],
                                    fault_code=sop["fault_code"],
                                    title=sop["title"],
                                    sop_markdown=sop["sop_markdown"],
                                    torque_spec=sop["torque_spec"],
                                    similarity_score=sim,
                                ),
                            )
                        )
                    scored.sort(key=lambda item: item[0], reverse=True)
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                    prov = StageProvenance(
                        stage="RETRIEVAL",
                        producer="MODEL",
                        model_id=model_id,
                        latency_ms=elapsed_ms,
                        input_simulated=input_simulated,
                        note=f"Real cosine similarity over {len(SEED_SOPS)} SOPs",
                    )
                    return [item[1] for item in scored[:limit]], prov
            except Exception as exc:  # noqa: BLE001 - logged, keyword fallback is labelled
                _log_retrieval_event("query_embedding_error", f"{type(exc).__name__}: {str(exc)[:120]}")

        # Labelled keyword fallback (zero forced similarity!)
        scored_kw = []
        for sop in SEED_SOPS:
            sim = _keyword_score(query_text, sop)
            scored_kw.append(
                (
                    sim,
                    MatchedSOPRecord(
                        id=sop["id"],
                        machine_type=sop["machine_type"],
                        fault_code=sop["fault_code"],
                        title=sop["title"],
                        sop_markdown=sop["sop_markdown"],
                        torque_spec=sop["torque_spec"],
                        similarity_score=sim,
                    ),
                )
            )
        scored_kw.sort(key=lambda item: item[0], reverse=True)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        prov = StageProvenance(
            stage="RETRIEVAL",
            producer="FALLBACK_RULES",
            model_id=None,
            latency_ms=elapsed_ms,
            input_simulated=input_simulated,
            note="KEYWORD FALLBACK",
        )
        return [item[1] for item in scored_kw[:limit]], prov

    def get_sop_by_id(self, sop_id: str) -> Optional[MatchedSOPRecord]:
        for sop in SEED_SOPS:
            if sop["id"] == sop_id:
                return MatchedSOPRecord(
                    id=sop["id"],
                    machine_type=sop["machine_type"],
                    fault_code=sop["fault_code"],
                    title=sop["title"],
                    sop_markdown=sop["sop_markdown"],
                    torque_spec=sop["torque_spec"],
                    similarity_score=1.0,
                )
        return None

    async def log_incident(
        self,
        incident_id: str,
        line: str,
        sample_id: Optional[str],
        line_name: str,
        tier1_status: str,
        defect_type: str,
        severity: str,
        root_cause: str,
        avoidable_loss_inr: int,
        inference_mode: str,
        latency_ms: int,
    ) -> None:
        conn = sqlite3.connect(self.sqlite_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO inspection_incidents
                (id, line, sample_id, line_name, tier1_status, defect_type, severity, root_cause, avoidable_loss_inr, inference_mode, latency_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    line,
                    sample_id,
                    line_name,
                    tier1_status,
                    defect_type,
                    severity,
                    root_cause,
                    avoidable_loss_inr,
                    inference_mode,
                    latency_ms,
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def record_disposition(self, incident_id: str, payload: DispositionCreate) -> DispositionRecord:
        recorded_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        conn = sqlite3.connect(self.sqlite_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO incident_dispositions
                (incident_id, decision, role, note, recorded_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (incident_id, payload.decision, payload.role, payload.note, recorded_at),
            )
            conn.commit()
        finally:
            conn.close()
        return DispositionRecord(
            incident_id=incident_id,
            decision=payload.decision,
            role=payload.role,
            note=payload.note,
            recorded_at=recorded_at,
        )

    def get_disposition(self, incident_id: str) -> Optional[DispositionRecord]:
        conn = sqlite3.connect(self.sqlite_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT incident_id, decision, role, note, recorded_at FROM incident_dispositions WHERE incident_id = ?",
                (incident_id,),
            )
            row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return DispositionRecord(
            incident_id=row[0],
            decision=row[1],
            role=row[2],
            note=row[3],
            recorded_at=row[4],
        )

    def _regex_extract_work_order(self, operator_notes: str, line: str) -> tuple[ExtractedWorkOrderTags, bool]:
        notes_lower = operator_notes.lower()
        sku_match = re.search(r"\b([A-Z]{2,10}-[A-Z0-9]{2,10}(?:-[A-Z0-9]{2,8})?)\b", operator_notes)
        if sku_match:
            part_code = sku_match.group(1)
        elif "bearing" in notes_lower or "spindle" in notes_lower or "बियरिंग" in operator_notes or line.upper() == "CNC":
            part_code = "SP-7014C-P4S"
        elif "weld" in notes_lower or "nozzle" in notes_lower or "gas" in notes_lower or "नोजल" in operator_notes or line.upper() == "WELD":
            part_code = "NOZ-MIG-16MM"
        else:
            part_code = "STENCIL-QFP-04MM"

        urgent_terms = [
            "immediate", "critical", "stoppage", "sla", "urgent", "spall",
            "bridge", "porosity", "halt", "hold", "तुरंत", "रोकें", "तात्काळ", "बंद",
        ]
        sla_risk = any(k in notes_lower or k in operator_notes for k in urgent_terms)
        priority = "P1_IMMEDIATE" if sla_risk else "P2_CURRENT_SHIFT"
        spares = {
            "SP-7014C-P4S": ["SP-7014C-P4S Duplex Angular Contact Bearing", "ISO-VG32 Mist Oil Cartridge"],
            "NOZ-MIG-16MM": ["NOZ-MIG-16MM Conical Gas Nozzle", "1.2mm CuCrZr Contact Tip"],
        }.get(part_code, ["ROL0 Desoldering Braid 1.0mm", "SAC305 Solder Paste Cartridge"])

        return (
            ExtractedWorkOrderTags(
                part_code=part_code,
                shift_priority=priority,
                required_spares=spares,
                sla_risk=sla_risk,
                sla_reason="Matched urgency keywords (rule-based fallback)" if sla_risk else "Standard shift maintenance",
            ),
            sla_risk,
        )

    async def create_work_order(
        self,
        payload: WorkOrderCreate,
        genai_client: Any = None,
    ) -> WorkOrderRecord:
        """Create a work order after verifying human disposition, extracting tags with Gemini + fallback."""
        disp = self.get_disposition(payload.incident_id)
        if disp is None or disp.decision not in ("HOLD", "REWORK", "SCRAP"):
            raise ValueError(
                "A human QE/Supervisor disposition of HOLD, REWORK, or SCRAP must be recorded before logging a work order."
            )

        wo_id = f"WO-{uuid.uuid4().hex[:6].upper()}"
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        tags: Optional[ExtractedWorkOrderTags] = None
        sla_critical = False
        producer = "FALLBACK_RULES"
        model_id: Optional[str] = None

        if genai_client is not None and genai_types is not None:
            try:
                extract_model = self.settings.wo_extract_model
                prompt = (
                    "Extract structured maintenance work-order fields from this shop-floor operator note "
                    "(which may be in English, Hindi, or Marathi).\n"
                    f"Line: {payload.line or 'PCB'} | Machine: {payload.machine_id}\n"
                    f"Operator Note: {payload.operator_notes}\n"
                    "Return JSON matching the schema with part_code, shift_priority, required_spares, sla_risk, sla_reason."
                )
                resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        genai_client.models.generate_content,
                        model=extract_model,
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=_WOExtractionSchema,
                            temperature=0.1,
                        ),
                    ),
                    timeout=8.0,
                )
                if resp and getattr(resp, "text", None):
                    parsed = _WOExtractionSchema.model_validate_json(resp.text.strip())
                    tags = ExtractedWorkOrderTags(
                        part_code=parsed.part_code,
                        shift_priority=parsed.shift_priority,
                        required_spares=parsed.required_spares,
                        sla_risk=parsed.sla_risk,
                        sla_reason=parsed.sla_reason,
                    )
                    sla_critical = parsed.sla_risk
                    producer = "MODEL"
                    model_id = extract_model
            except Exception:
                tags = None

        if tags is None:
            tags, sla_critical = self._regex_extract_work_order(payload.operator_notes, payload.line or "PCB")
            producer = "FALLBACK_RULES"
            model_id = None

        conn = sqlite3.connect(self.sqlite_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO work_orders
                (id, incident_id, machine_id, operator_notes, extracted_tags_json, sla_critical_flag,
                 extraction_producer, extraction_model_id, status, avoidable_loss_inr, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
                """,
                (
                    wo_id,
                    payload.incident_id,
                    payload.machine_id,
                    payload.operator_notes,
                    json.dumps(tags.model_dump()),
                    1 if sla_critical else 0,
                    producer,
                    model_id,
                    payload.avoidable_loss_inr,
                    created_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return WorkOrderRecord(
            id=wo_id,
            incident_id=payload.incident_id,
            machine_id=payload.machine_id,
            operator_notes=payload.operator_notes,
            extracted_tags_json=tags,
            sla_critical_flag=sla_critical,
            extraction_producer=producer,
            extraction_model_id=model_id,
            status="OPEN",
            avoidable_loss_inr=payload.avoidable_loss_inr,
            created_at=created_at,
        )

    async def list_work_orders(self, limit: int = 25) -> list[WorkOrderRecord]:
        conn = sqlite3.connect(self.sqlite_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, incident_id, machine_id, operator_notes, extracted_tags_json,
                       sla_critical_flag, extraction_producer, extraction_model_id, status,
                       avoidable_loss_inr, created_at
                FROM work_orders
                ORDER BY rowid DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        return [
            WorkOrderRecord(
                id=r[0],
                incident_id=r[1],
                machine_id=r[2],
                operator_notes=r[3],
                extracted_tags_json=ExtractedWorkOrderTags(**json.loads(r[4])),
                sla_critical_flag=bool(r[5]),
                extraction_producer=str(r[6] or "FALLBACK_RULES"),
                extraction_model_id=r[7],
                status=r[8],
                avoidable_loss_inr=int(r[9] or 0),
                created_at=r[10],
            )
            for r in rows
        ]
