#!/usr/bin/env python3
"""Phase 4a: Benchmark candidate Tier-2 models on 8 escalated mock-rig samples.

Decision rule:
  Highest defect-type agreement with p95 <= 10 s; ties go to the faster model.
Writes results to `eval/model_selection.md` and `eval/model_selection.json`.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from google import genai
from google.genai import types as genai_types

from backend.config import PROJECT_ROOT, get_settings
from backend.dsp.envelope import evaluate_t1a_signal_gate
from backend.mock_rig.dataset import MANIFEST_PATH, ensure_dataset, load_sample_public
from backend.schemas import MatchedSOPRecord, SensorTelemetry
from backend.services.model_router import Tier2ModelOutput, _strip_json_fences
from backend.services.skill_loader import get_skill_loader


CANDIDATES = [
    "gemini-4-hydrogen",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]


def _pick_8_defect_samples() -> list[dict[str, Any]]:
    ensure_dataset()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    chosen: list[dict[str, Any]] = []
    quotas = {"PCB": 3, "CNC": 3, "WELD": 2}
    counts = {"PCB": 0, "CNC": 0, "WELD": 0}
    for entry in manifest:
        line = entry["line"]
        if entry["is_defect"] and counts[line] < quotas[line]:
            chosen.append(entry)
            counts[line] += 1
    return chosen


def main() -> None:
    api_key = (os.getenv("GEMINI_API_KEY", "") or get_settings().gemini_api_key).strip()
    candidates = sys.argv[1].split(",") if len(sys.argv) > 1 else CANDIDATES
    assert api_key, "GEMINI_API_KEY required"
    client = genai.Client(api_key=api_key, http_options=genai_types.HttpOptions(timeout=15000))
    skill_loader = get_skill_loader()
    samples = _pick_8_defect_samples()

    # Minimal neutral SOP candidates (3 per line) so retrieval doesn't bias benchmark
    mock_sops = {
        "PCB": [
            MatchedSOPRecord(id="SOP-PUNE-PCB-01", machine_type="PCB", fault_code="SOLDER_BRIDGE", title="QFP Solder Bridge", sop_markdown="Wick excess solder at 330°C with 1.0 mm braid; check >0.15 mm clearance.", torque_spec="4.5 Nm"),
            MatchedSOPRecord(id="SOP-PUNE-PCB-02", machine_type="PCB", fault_code="INSUFFICIENT_SOLDER", title="Insufficient Solder Fillet", sop_markdown="Check paste aperture and reflow peak 235-250°C, TAL 45-90 s.", torque_spec="4.5 Nm"),
            MatchedSOPRecord(id="SOP-PUNE-PCB-03", machine_type="PCB", fault_code="FLUX_GLARE", title="Cosmetic Flux Residue", sop_markdown="Verify clearance >0.15 mm; no rework if nominal.", torque_spec="N/A"),
        ],
        "CNC": [
            MatchedSOPRecord(id="SOP-PUNE-CNC-01", machine_type="CNC", fault_code="OUTER_RACE_FAULT", title="Spindle Bearing Outer-Race Fault", sop_markdown="M01 feed-hold, replace SP-7014C-P4S bearing set, flush mist at 0.35 MPa, verify <0.003 mm TIR.", torque_spec="145 Nm"),
            MatchedSOPRecord(id="SOP-PUNE-CNC-02", machine_type="CNC", fault_code="IMBALANCE", title="Spindle/Toolholder Imbalance", sop_markdown="Inspect toolholder balance at 5400 rpm; check 1x harmonic.", torque_spec="75 Nm"),
            MatchedSOPRecord(id="SOP-PUNE-CNC-03", machine_type="CNC", fault_code="TRANSIENT", title="Transient Impact Check", sop_markdown="Log transient event; resume if no BPFO periodicity.", torque_spec="N/A"),
        ],
        "WELD": [
            MatchedSOPRecord(id="SOP-PUNE-WELD-01", machine_type="WELD", fault_code="POROSITY_GAS_LOSS", title="MIG Weld Seam Porosity", sop_markdown="Grind porous bead, replace NOZ-MIG-16MM nozzle & 1.2 mm tip, restore 16.5 L/min gas.", torque_spec="22 Nm"),
            MatchedSOPRecord(id="SOP-PUNE-WELD-02", machine_type="WELD", fault_code="SPATTER_COSMETIC", title="Cosmetic Weld Spatter", sop_markdown="Clean plate spatter if bead is sound and gas 15-20 L/min.", torque_spec="22 Nm"),
            MatchedSOPRecord(id="SOP-PUNE-WELD-03", machine_type="WELD", fault_code="WIRE_FEED", title="MIG Wire Feed Slip", sop_markdown="Check drive roll tension and 20-24 V arc stability.", torque_spec="22 Nm"),
        ],
    }

    summary: list[dict[str, Any]] = []
    for model_id in candidates:
        ok_count = 0
        schema_valid = 0
        agree_count = 0
        latencies: list[int] = []
        in_tokens: list[int] = []
        out_tokens: list[int] = []
        errors: list[str] = []

        for entry in samples:
            sid = entry["sample_id"]
            line = entry["line"]
            pub = load_sample_public(sid)
            telemetry = SensorTelemetry(**pub["telemetry"])
            wav_path = Path(pub["wav_path"]) if pub.get("wav_path") else None
            t1a = evaluate_t1a_signal_gate(line=line, telemetry=telemetry, wav_path=wav_path)
            skill = skill_loader.activate_skill_for_line(line, t1a.all_flags)
            sops = mock_sops[line]
            sop_txt = "\n".join(f"- [{s.id}] {s.title}: {s.sop_markdown} (Spec: {s.torque_spec})" for s in sops)
            raw_img = Path(pub["frame_path"]).read_bytes()

            prompt = (
                "You are Vinyas Tier-2 Multimodal Root-Cause Engine.\n"
                f"Line: {line}\nTelemetry: {telemetry.model_dump_json()}\n"
                f"DSP Features: {json.dumps(t1a.features)}\nFlags: {json.dumps(t1a.all_flags)}\n"
                f"Skill:\n{skill['skill_markdown']}\nSOPs:\n{sop_txt}\n"
                "Classify defect_type strictly from: SOLDER_BRIDGE, INSUFFICIENT_SOLDER, OUTER_RACE_FAULT, "
                "IMBALANCE, POROSITY_GAS_LOSS, NO_DEFECT_FOUND, OTHER."
            )
            parts: list[Any] = [genai_types.Part.from_bytes(data=raw_img, mime_type="image/png")]
            if t1a.envelope_png_bytes:
                parts.append(genai_types.Part.from_bytes(data=t1a.envelope_png_bytes, mime_type="image/png"))
            parts.append(prompt)

            t0 = time.perf_counter()
            try:
                for attempt in range(2):  # one retry on free-tier 429/503, after waiting out the minute window
                    t0 = time.perf_counter()
                    try:
                        resp = client.models.generate_content(
                            model=model_id,
                            contents=parts,
                            config=genai_types.GenerateContentConfig(
                                response_mime_type="application/json",
                                response_schema=Tier2ModelOutput,
                                temperature=0.15,
                            ),
                        )
                        break
                    except Exception as retry_exc:  # noqa: BLE001
                        if attempt == 0 and ("429" in str(retry_exc) or "503" in str(retry_exc)):
                            time.sleep(20.0)
                            continue
                        raise
                ms = int((time.perf_counter() - t0) * 1000)
                latencies.append(ms)
                ok_count += 1
                usage = getattr(resp, "usage_metadata", None)
                if usage:
                    if getattr(usage, "prompt_token_count", None):
                        in_tokens.append(int(usage.prompt_token_count))
                    if getattr(usage, "candidates_token_count", None):
                        out_tokens.append(int(usage.candidates_token_count))
                parsed = Tier2ModelOutput.model_validate_json(_strip_json_fences(resp.text))
                schema_valid += 1
                if parsed.defect_type == entry["defect_type"]:
                    agree_count += 1
            except Exception as exc:
                ms = int((time.perf_counter() - t0) * 1000)
                latencies.append(ms)
                errors.append(f"{sid}: {type(exc).__name__}: {str(exc)[:90]}")

        lat_sorted = sorted(latencies)
        p50 = int(statistics.median(lat_sorted)) if lat_sorted else 0
        p75 = int(lat_sorted[min(len(lat_sorted) - 1, int(0.75 * len(lat_sorted)))]) if lat_sorted else 0
        p95 = int(lat_sorted[min(len(lat_sorted) - 1, int(0.95 * len(lat_sorted)))]) if lat_sorted else 0
        row = {
            "model_id": model_id,
            "n": len(samples),
            "success_rate": f"{ok_count}/{len(samples)}",
            "schema_valid_rate": f"{schema_valid}/{len(samples)}",
            "agreement": f"{agree_count}/{len(samples)}",
            "agreement_num": agree_count,
            "p50_ms": p50,
            "p75_ms": p75,
            "p95_ms": p95,
            "mean_in_tokens": int(statistics.mean(in_tokens)) if in_tokens else 0,
            "mean_out_tokens": int(statistics.mean(out_tokens)) if out_tokens else 0,
            "errors": errors[:3],
        }
        summary.append(row)
        print(json.dumps(row), flush=True)

    # Decision rule: highest agreement with p95 <= 10_000 ms; ties -> lower p50
    eligible = [r for r in summary if r["p95_ms"] <= 10_000 and r["agreement_num"] > 0]
    ranked = sorted(eligible or summary, key=lambda r: (-r["agreement_num"], r["p50_ms"]))
    primary = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else ranked[0]

    md_lines = [
        "# Tier-2 Model Selection Benchmark (`eval/model_selection.md`)",
        "",
        "Measured on **8 escalated simulated defect samples** from `backend/mock_rig` (3 PCB, 3 CNC, 2 WELD) using the full multimodal Tier-2 payload (frame PNG + CNC Hilbert envelope PNG + DSP features + SOPs + SKILL.md + strict Pydantic `response_schema`).",
        "",
        "**Decision rule:** Highest defect-type agreement with `p95 <= 10,000 ms`; ties go to the faster (`p50`) model.",
        "",
        "| Model ID | Success | Schema Valid | Defect Agreement | p50 (ms) | p75 (ms) | p95 (ms) | Mean In Tok | Mean Out Tok |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in summary:
        md_lines.append(
            f"| `{r['model_id']}` | {r['success_rate']} | {r['schema_valid_rate']} | {r['agreement']} "
            f"| {r['p50_ms']} | {r['p75_ms']} | {r['p95_ms']} | {r['mean_in_tokens']} | {r['mean_out_tokens']} |"
        )
    md_lines.extend(
        [
            "",
            "## Routing Decision",
            f"- **Primary:** `{primary['model_id']}` (agreement `{primary['agreement']}`, p50 `{primary['p50_ms']} ms`, p95 `{primary['p95_ms']} ms`)",
            f"- **Runner-up (hedged):** `{runner_up['model_id']}` (agreement `{runner_up['agreement']}`, p50 `{runner_up['p50_ms']} ms`, p95 `{runner_up['p95_ms']} ms`)",
            f"- **Hedge trigger delay:** `min(primary p75, 6.0 s)` = `{min(primary['p75_ms'] / 1000.0, 6.0):.2f} s`",
        ]
    )
    out_md = PROJECT_ROOT / "eval" / "model_selection.md"
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    (PROJECT_ROOT / "eval" / "model_selection.json").write_text(
        json.dumps({"summary": summary, "primary": primary["model_id"], "runner_up": runner_up["model_id"]}, indent=2),
        encoding="utf-8",
    )
    print(f"\nWrote {out_md}")


if __name__ == "__main__":
    main()
