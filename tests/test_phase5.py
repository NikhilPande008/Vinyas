"""Phase 5 unit tests: 18-SOP retrieval, disposition gating, WO extraction, schema honesty."""

from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.config import PROJECT_ROOT
from backend.db.demo_store import SEED_SOPS, DemoStoreService
from backend.main import app, demo_store, model_router


def test_18_sops_and_distinct_queries_return_distinct_top1():
    assert len(SEED_SOPS) == 18
    store = DemoStoreService(sqlite_path=str(PROJECT_ROOT / ".pytest_cache" / "test_p5_ret.db"))
    import asyncio

    sops_pcb, prov1 = asyncio.run(store.search_sops("QFP solder bridge reflow ramp", genai_client=None, limit=3))
    sops_cnc, prov2 = asyncio.run(store.search_sops("spindle bearing BPFO outer race 793 Hz", genai_client=None, limit=3))
    sops_weld, prov3 = asyncio.run(store.search_sops("MIG weld porosity shielding gas nozzle", genai_client=None, limit=3))

    assert prov1.note == "KEYWORD FALLBACK"
    assert sops_pcb[0].id != sops_cnc[0].id
    assert sops_cnc[0].id != sops_weld[0].id
    assert sops_pcb[0].id == "SOP-PCB-01"
    assert sops_cnc[0].id == "SOP-CNC-01"
    assert sops_weld[0].id == "SOP-WELD-01"
    # Verify no forced 0.96 override
    assert all(s.similarity_score != 0.96 for s in sops_pcb + sops_cnc + sops_weld)

    # Verify line-scoped retrieval never returns cross-line distractors
    sops_cnc_scoped, _ = asyncio.run(
        store.search_sops("solder bridge porosity", genai_client=None, limit=3, line="CNC")
    )
    assert len(sops_cnc_scoped) == 3
    assert all(s.machine_type == "CNC_SPINDLE" for s in sops_cnc_scoped)

    sops_pcb_scoped, _ = asyncio.run(
        store.search_sops("insufficient solder cold joint starved pads", genai_client=None, limit=3, line="PCB")
    )
    assert all(s.machine_type == "SMT_REFLOW_PCB" for s in sops_pcb_scoped)
    assert sops_pcb_scoped[0].id == "SOP-PCB-02"


def test_disposition_required_before_work_order_and_multilingual_extract():
    import uuid

    client = TestClient(app)
    inc_id = f"INC-TEST-DISP-{uuid.uuid4().hex[:6]}"

    # Without disposition -> 400
    r1 = client.post(
        "/api/work-orders",
        json={
            "incident_id": inc_id,
            "machine_id": "CNC-SPINDLE-CHAKAN-B2",
            "operator_notes": "तुरंत स्पिंडल रोकें, बियरिंग SP-7014C-P4S बदलना है",
            "line": "CNC",
            "avoidable_loss_inr": 10000,
        },
    )
    assert r1.status_code == 400

    # With RELEASE disposition -> still 400
    d_rel = client.post(
        f"/api/incidents/{inc_id}/disposition",
        json={"decision": "RELEASE", "role": "QE", "note": "Looks ok"},
    )
    assert d_rel.status_code == 200
    r2 = client.post(
        "/api/work-orders",
        json={
            "incident_id": inc_id,
            "machine_id": "CNC-SPINDLE-CHAKAN-B2",
            "operator_notes": "तुरंत स्पिंडल रोकें, बियरिंग SP-7014C-P4S बदलना है",
            "line": "CNC",
            "avoidable_loss_inr": 10000,
        },
    )
    assert r2.status_code == 400

    # With HOLD disposition -> succeeds (offline regex fallback handles Hindi note)
    orig_client = model_router._client
    model_router.set_client(None)
    try:
        d_hold = client.post(
            f"/api/incidents/{inc_id}/disposition",
            json={"decision": "HOLD", "role": "Supervisor", "note": "Confirmed BPFO"},
        )
        assert d_hold.status_code == 200
        r3 = client.post(
            "/api/work-orders",
            json={
                "incident_id": inc_id,
                "machine_id": "CNC-SPINDLE-CHAKAN-B2",
                "operator_notes": "तुरंत स्पिंडल रोकें, बियरिंग SP-7014C-P4S बदलना है",
                "line": "CNC",
                "avoidable_loss_inr": 10000,
            },
        )
        assert r3.status_code == 200
        wo = r3.json()
        assert wo["extracted_tags_json"]["part_code"] == "SP-7014C-P4S"
        assert wo["sla_critical_flag"] is True
        assert wo["extraction_producer"] == "FALLBACK_RULES"
    finally:
        model_router.set_client(orig_client)


def test_alloydb_production_schema_has_no_constant_vectors():
    sql = (PROJECT_ROOT / "infra" / "alloydb_schema.sql").read_text(encoding="utf-8")
    assert "array_fill" not in sql.lower()
    assert "vector(768)" in sql
    assert "not deployed" in sql.lower()
    assert "tata motors" not in sql.lower()
