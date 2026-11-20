#!/usr/bin/env python3
"""Vinyas — Optional On-Prem Edge Client (`edge_client/edge_gateway.py`).

NOT part of the hosted Cloud Run demo; requires a local Ollama instance running
a Gemma model (e.g. `gemma4:e4b`). Reuses `backend/dsp/envelope.py` for deterministic
T1-A signal gating and calls Ollama for T1-B visual gating with fail-safe escalation.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from backend.dsp.envelope import evaluate_t1a_signal_gate
from backend.mock_rig.dataset import draw_random_sample, load_sample_public
from backend.schemas import SensorTelemetry


OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EDGE_MODEL = os.getenv("EDGE_GEMMA_MODEL_ID", "gemma4:e4b")
CLOUD_RUN_API_URL = os.getenv("CLOUD_RUN_BACKEND_URL", "http://localhost:8080")


def local_edge_gate(
    line: str,
    telemetry: SensorTelemetry,
    image_path: Path,
    wav_path: Path | None = None,
    ollama_timeout_sec: float = 5.0,
) -> dict[str, Any]:
    """Run deterministic T1-A DSP + local Ollama Gemma T1-B with fail-safe escalation."""
    t0 = time.perf_counter()
    t1a = evaluate_t1a_signal_gate(line=line, telemetry=telemetry, wav_path=wav_path)

    img_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    t1b_vote = "UNAVAILABLE"
    t1b_reason = "Local Ollama model unavailable -> fail-safe escalation"

    try:
        prompt = (
            f"Inspect this {line} manufacturing part frame and sensor features.\n"
            f"T1-A features: {json.dumps(t1a.features)}\n"
            f"T1-A flags: {json.dumps(t1a.all_flags)}\n"
            'Return JSON only: {"vote": "NOMINAL"|"ANOMALY", "reason": "short string"}'
        )
        with httpx.Client(timeout=ollama_timeout_sec) as client:
            resp = client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": EDGE_MODEL,
                    "prompt": prompt,
                    "images": [img_b64],
                    "stream": False,
                    "format": "json",
                },
            )
            if resp.status_code == 200:
                parsed = json.loads(resp.json().get("response", "{}"))
                vote = str(parsed.get("vote", "")).upper()
                if vote in ("NOMINAL", "ANOMALY"):
                    t1b_vote = vote
                    t1b_reason = str(parsed.get("reason") or f"Ollama {EDGE_MODEL} voted {vote}")
    except Exception as exc:
        t1b_reason = f"Ollama error ({type(exc).__name__}) -> fail-safe escalation"

    escalate = t1a.any_escalating_flag or t1b_vote != "NOMINAL"
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "pass_status": "ESCALATE" if escalate else "HEALTHY",
        "t1a_flags": t1a.all_flags,
        "t1b_vote": t1b_vote,
        "reason": t1b_reason if not t1a.any_escalating_flag else f"{t1a.summary} | {t1b_reason}",
        "model": f"{EDGE_MODEL} (Ollama on-prem)",
        "measured_latency_ms": elapsed_ms,
    }


def run_edge_cycle(line: str, sample_id: str | None, cloud_url: str) -> dict[str, Any]:
    sample = load_sample_public(sample_id) if sample_id else draw_random_sample(line)
    telemetry = SensorTelemetry(**sample["telemetry"])
    wav_path = Path(sample["wav_path"]) if sample.get("wav_path") else None
    triage = local_edge_gate(
        line=sample["line"],
        telemetry=telemetry,
        image_path=Path(sample["frame_path"]),
        wav_path=wav_path,
    )
    if triage["pass_status"] == "HEALTHY":
        return {"sample_id": sample["sample_id"], "edge_triage": triage, "cloud_escalated": False}

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{cloud_url.rstrip('/')}/api/inspect",
            json={"sample_id": sample["sample_id"]},
        )
        resp.raise_for_status()
        return {
            "sample_id": sample["sample_id"],
            "edge_triage": triage,
            "cloud_escalated": True,
            "cloud_response": resp.json(),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vinyas Optional On-Prem Edge Client (Ollama)")
    parser.add_argument("--line", default="CNC", choices=["PCB", "CNC", "WELD"])
    parser.add_argument("--sample-id", default=None)
    parser.add_argument("--cloud-url", default=CLOUD_RUN_API_URL)
    args = parser.parse_args()
    print(json.dumps(run_edge_cycle(args.line, args.sample_id, args.cloud_url), indent=2))
