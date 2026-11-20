#!/usr/bin/env python3
"""Phase 10: Live deployment verification script (`scripts/verify_live.py`).

Checks a deployed Vinyas URL and writes `eval/live_verification.md`:
1. Path traversal blocked on SPA catch-all
2. /health and /api/metrics truthful
3. Random draws across PCB, CNC, WELD produce real provenance and varying verdicts
4. Custom upload of healthy vs defective images on each line
5. Co-pilot in EN / hi-IN / mr-IN
6. Disposition required before work order, then work order succeeds
7. Rate limiter returns HTTP 429 after quota
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from backend.config import PROJECT_ROOT
from backend.mock_rig.dataset import MANIFEST_PATH, SAMPLES_DIR, ensure_dataset


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check_rate_limit = "--check-rate-limit" in sys.argv
    if not args:
        print("Usage: python3 scripts/verify_live.py <BASE_URL> [--check-rate-limit]")
        sys.exit(1)

    base = args[0].rstrip("/")
    ensure_dataset()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    results: list[str] = [
        "# Live Deployment Verification (`eval/live_verification.md`)",
        "",
        f"- **Target URL:** {base}",
        f"- **Timestamp (UTC):** {datetime.now(timezone.utc).isoformat()}",
        "",
    ]

    with httpx.Client(timeout=45.0) as client:
        # 1. Path traversal check (using raw request path)
        trav_resp = client.get(f"{base}/..%2f..%2frequirements.txt")
        trav_ok = trav_resp.status_code in (200, 404) and "fastapi==" not in trav_resp.text.lower()
        results.append(f"## 1. Security — Path Traversal")
        results.append(f"- `GET /..%2f..%2frequirements.txt` → HTTP `{trav_resp.status_code}` | Blocked: `{trav_ok}`")
        results.append("")

        # 2. /health and /api/metrics
        h = client.get(f"{base}/health").json()
        m = client.get(f"{base}/api/metrics").json()
        results.append("## 2. Health & Metrics")
        results.append(f"- `storage_mode`: `{h.get('storage_mode')}` (`{h.get('storage_note')}`)")
        results.append(f"- `retrieval_mode`: `{h.get('retrieval_mode')}`")
        results.append(f"- `routing_config`: `{json.dumps(h.get('routing_config', {}))}`")
        results.append(f"- `/api/metrics` keys: `{list(m.keys())}`")
        results.append("")

        # 3. Random draws per line (4 per line to stay inside 30/10m rate limit during smoke check)
        results.append("## 3. Blind Draws & Provenance")
        verdicts: set[str] = set()
        lats: list[int] = []
        last_inc_id = None
        for line in ("PCB", "CNC", "WELD"):
            for _ in range(3):
                d = client.post(f"{base}/api/rig/draw", json={"line": line}).json()
                sid = d["sample_id"]
                t0 = time.perf_counter()
                r = client.post(f"{base}/api/inspect", json={"sample_id": sid})
                ms = int((time.perf_counter() - t0) * 1000)
                lats.append(ms)
                if r.status_code == 200:
                    body = r.json()
                    v = body["tier1_triage"]["pass_status"]
                    verdicts.add(v)
                    last_inc_id = body["incident_id"]
                    rev = client.get(f"{base}/api/rig/reveal/{sid}").json()
                    results.append(
                        f"- `{sid}` (`{line}`): gate=`{v}`, gt=`{rev.get('defect_type')}`, "
                        f"t1_model=`{body['telemetry'].get('tier1_model_used')}`, "
                        f"t2_model=`{body['telemetry'].get('tier2_model_used')}`, wall=`{ms} ms`"
                    )
                else:
                    results.append(f"- `{sid}` (`{line}`): HTTP `{r.status_code}`")
        p50 = int(statistics.median(lats)) if lats else 0
        p95 = int(sorted(lats)[min(len(lats) - 1, int(0.95 * len(lats)))]) if lats else 0
        results.append(f"- **Observed verdicts:** `{sorted(verdicts)}` | p50=`{p50} ms` | p95=`{p95} ms`")
        results.append("")

        # 4. Upload test: one healthy and one defect image per line (uploads use nominal telemetry
        #    unless the operator picks a preset, so PCB/WELD verdicts come from the visual gate).
        #    CNC frames never show the bearing, so the CNC "defect" upload carries Zone-C vibration
        #    telemetry, which is how a CNC fault must be detected.
        results.append("## 4. Custom Upload Test (healthy vs defect, every line)")
        upload_cases = [
            ("PCB", "NOMINAL", None),
            ("PCB", "SOLDER_BRIDGE", None),
            ("WELD", "NOMINAL", None),
            ("WELD", "POROSITY_GAS_LOSS", None),
            ("CNC", "NOMINAL", None),
            ("CNC", "OUTER_RACE_FAULT", {"vibration_khz": 0.793, "vibration_rms_mms": 5.1, "temperature_c": 62.0, "line_speed_rpm": 5400}),
        ]
        for line, dtype, telemetry in upload_cases:
            entry = next(x for x in manifest if x["line"] == line and x["defect_type"] == dtype)
            b64 = base64.b64encode((SAMPLES_DIR / entry["sample_id"] / "frame.png").read_bytes()).decode("ascii")
            payload: dict = {"line": line, "custom_image_base64": b64}
            if telemetry:
                payload["sensor_telemetry"] = telemetry
            r = client.post(f"{base}/api/inspect", json=payload)
            expected = "HEALTHY" if dtype == "NOMINAL" else "ESCALATE"
            if r.status_code == 200:
                body = r.json()
                tri = body["tier1_triage"]
                got = tri["pass_status"]
                results.append(
                    f"- {line} {dtype} upload (`{entry['sample_id']}`{', Zone-C telemetry' if telemetry else ''}): "
                    f"gate=`{got}` (expected `{expected}`, {'OK' if got == expected else 'MISMATCH'}), "
                    f"visual vote=`{tri.get('t1b_vote')}` by `{tri['provenance_t1b'].get('model_id')}`, "
                    f"input_simulated=`{body['input_simulated']}`"
                )
            else:
                results.append(f"- {line} {dtype} upload: HTTP `{r.status_code}`")
        results.append("")

        # 5. Co-pilot in 3 languages
        results.append("## 5. Co-Pilot Multilingual Check")
        for lang, q in (
            ("en-IN", "What is the spindle bearing locknut torque spec?"),
            ("hi-IN", "स्पिंडल बियरिंग का टॉर्क कितना है?"),
            ("mr-IN", "स्पिंडल बेअरिंगचा टॉर्क किती आहे?"),
        ):
            r = client.post(f"{base}/api/copilot/chat", json={"question": q, "line": "CNC", "language": lang})
            if r.status_code == 200:
                c = r.json()
                results.append(
                    f"- `{lang}`: model=`{c.get('model_used') or c.get('producer')}`, "
                    f"audio=`{bool(c.get('audio_wav_base64'))}`, latency=`{c.get('latency_ms')} ms`"
                )
        results.append("")

        # 6. Disposition -> Work Order
        results.append("## 6. Disposition & Work Order Gating")
        if last_inc_id:
            wo_before = client.post(
                f"{base}/api/work-orders",
                json={"incident_id": last_inc_id, "machine_id": "CNC-SPINDLE-CHAKAN-B2", "operator_notes": "Hold bearing SP-7014C-P4S", "line": "CNC"},
            )
            d_resp = client.post(
                f"{base}/api/incidents/{last_inc_id}/disposition",
                json={"decision": "HOLD", "role": "QE", "note": "Live verification hold"},
            )
            wo_after = client.post(
                f"{base}/api/work-orders",
                json={"incident_id": last_inc_id, "machine_id": "CNC-SPINDLE-CHAKAN-B2", "operator_notes": "तुरंत स्पिंडल रोकें, SP-7014C-P4S बदलना है", "line": "CNC"},
            )
            results.append(f"- Before disposition: HTTP `{wo_before.status_code}` (expected 400)")
            results.append(f"- Record HOLD disposition: HTTP `{d_resp.status_code}`")
            results.append(f"- After disposition: HTTP `{wo_after.status_code}` (producer=`{wo_after.json().get('extraction_producer') if wo_after.status_code == 200 else 'err'}`)")

        # 7. Rate limiter (opt-in: it locks this IP out of /api/inspect for up to 10 minutes).
        #    Uses malformed sample_ids, which are rejected AFTER the limiter charges a token, so no
        #    model calls are spent.
        if check_rate_limit:
            results.append("")
            results.append("## 7. Rate Limiter")
            codes: list[int] = []
            for _ in range(40):
                rr = client.post(f"{base}/api/inspect", json={"sample_id": "bad id!"})
                codes.append(rr.status_code)
                if rr.status_code == 429:
                    break
            first_429 = codes.index(429) + 1 if 429 in codes else None
            results.append(
                f"- Malformed requests until HTTP 429: `{first_429}` (limit 30 per 10 min per IP; "
                f"earlier inspections in this run also consumed tokens)"
            )

    out_path = PROJECT_ROOT / "eval" / "live_verification.md"
    out_path.write_text("\n".join(results) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
