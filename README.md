# Vinyas — AI-Assisted Manufacturing Quality & Predictive Maintenance

Vinyas is a multi-modal inspection, SOP-grounded root-cause triage, and multilingual shop-floor co-pilot built for **shop-floor operators and quality engineers** on discrete automotive lines (SMT PCB reflow, CNC spindle machining, and robotic MIG welding).

**Live Cloud Run URL:** https://vinyas-ai-65216244490.asia-south1.run.app

### Try It in 3 Steps (Blind Mode)
1. **Select a line** (`PCB`, `CNC`, or `WELD`) and click **Draw random part** (hidden ground truth; no answer text on frames).
2. Click **Inspect part** to run deterministic DSP + Google AI gating, SOP retrieval, root-cause diagnosis, and model-located bbox overlay.
3. Click **Reveal ground truth** to compare the system's verdict against the hidden manifest, then record a human disposition (`RELEASE / HOLD / REWORK / SCRAP`) and log a multilingual work order.

---

## What Is Real vs Simulated

Per Startup Buildathon India 2026 organiser ruling, physical factory hardware is **not required**. Simulated inputs are permitted when they are physically plausible, leak no answers, and are explicitly labelled.

| Component | Status | Details |
| --- | --- | --- |
| Camera frames, 48 kHz WAV vibration, process telemetry | **SIMULATED INPUT** | Generated deterministically by `backend/mock_rig/` (60 seeded samples, zero text on images, ground truth isolated in `data/mock_rig/manifest.json` which inference never reads). Always badged `SIMULATED INPUT`. |
| Tier-1A Signal & Process Gate | **REAL (Deterministic DSP)** | NumPy/SciPy 2–8 kHz Butterworth bandpass → `\|hilbert\|` envelope → FFT → computed BPFO/2×BPFO SNR, kurtosis, ISO 20816-3 reference zones, SAC305 & MIG process windows (`backend/dsp/envelope.py`). |
| Tier-1B Visual Gate, Retrieval, Tier-2 Diagnosis, Tier-4 Co-Pilot, WO Extraction | **REAL (Google AI API)** | Live `google-genai` SDK calls with per-stage `StageProvenance` naming the exact `model_id`, latency, attempts, and token counts. |
| Tier-3 Visual Repair Overlay | **REAL (Deterministic render of AI bbox)** | Pillow draws a bounding box **only** from the model's returned `bbox` (`0..1000` scaled to actual image dimensions); draws no box when no defect is found. Nano Banana image models are **not** used at runtime (all 4 returned `429 RESOURCE_EXHAUSTED` on this key). |
| Incident, Disposition & Work Order Storage | **DEMO STORE (SQLite)** | Local SQLite (`backend/db/demo_store.py`) — resets when the Cloud Run container restarts. Production PostgreSQL + `pgvector(768)` schema is documented in `infra/alloydb_schema.sql` (not deployed). |
| Machine / PLC Actuation | **NOT BUILT (By Design)** | AI recommends only. A human QE or Supervisor records every disposition. |

---

## Architecture

```mermaid
flowchart LR
    MR["Mock Rig v2 (SIMULATED INPUT)\n60 seeded samples, hidden manifest"] --> T1A["T1-A: Deterministic DSP\nbackend/dsp/envelope.py\nBPFO Hilbert FFT / Process Windows"]
    MR --> T1B["T1-B: Visual/Context Gate\ngemma-4-26b-a4b-it\n(fallback: gemini-3.1-flash-lite)"]
    T1A --> GATE{"Fail-Safe Gate\nbackend/services/gate.py"}
    T1B --> GATE
    GATE -- "Both Nominal" --> PASS["HEALTHY\n(0 Tier-2 tokens)"]
    GATE -- "Any Flag / Error" --> RET["SOP Retrieval (18 SOPs)\ngemini-embedding-2 cosine\n(fallback: keyword)"]
    RET --> T2["T2: Root-Cause Diagnosis\nHedged: gemini-3.1-flash-lite / gemini-3.8-flash\n+ Active SKILL.md"]
    T2 --> GUARD["SOP Numeric Guard\nbackend/services/sop_guard.py"]
    T2 --> ECON["Deterministic Economics\nbackend/services/economics.py"]
    T2 --> T3["T3: Deterministic Overlay\nbackend/services/overlay.py\n(Model bbox only)"]
    T2 --> T4["T4: Floor Co-Pilot\nWS /api/live-copilot\ngemini-3.8-live (EN/HI/MR audio)"]
    T2 --> DISP["Human Disposition Gate\nQE / Supervisor\nRELEASE | HOLD | REWORK | SCRAP"]
    DISP -- "HOLD / REWORK / SCRAP" --> WO["Work Order Extraction\ngemini-3.1-flash-lite\n-> Demo SQLite Store"]
```

---

## Google AI Models Used (Verified & Measured)

Model routing was selected by live benchmark in [eval/model_selection.md](eval/model_selection.md). `gemini-4-hydrogen` scored `0/8` (timeouts/503) in the benchmark and was removed from routing.

| Role | Exact Model ID | Code Location | Why This Model | Fallback (Labelled) | Measured p50 |
| --- | --- | --- | --- | --- | ---: |
| T1-A Signal Gate | Deterministic DSP (NumPy/SciPy) | `backend/dsp/envelope.py:evaluate_t1a_signal_gate` | Millisecond Hilbert envelope FFT & window checks; an LLM should not run FFTs. | None needed | `0 ms` (p95 `10 ms`) |
| T1-B Visual Gate | `gemma-4-26b-a4b-it` | `backend/services/model_router.py:run_tier1_visual_gate` | Cloud-served stand-in for an on-prem Gemma edge model; screens frames before Tier-2. | `gemini-3.1-flash-lite`, then fail-safe `ESCALATE` | `4,933 ms` (p95 `8,053 ms`) |
| SOP Retrieval | `gemini-embedding-2` (`768-D`) | `backend/db/demo_store.py:search_sops` | Real cosine similarity across 18 SOPs (including distractors), cached in SQLite. | `KEYWORD FALLBACK` | Measured per request |
| T2 Root-Cause Diagnosis | `gemini-3.1-flash-lite` (primary), hedged with `gemini-3.8-flash` | `backend/services/model_router.py:run_tier2_multimodal_diagnosis` | Highest live availability & agreement in `eval/model_selection.md`; strict Pydantic schema + bbox. | `FALLBACK_RULES` (AI unavailable) | `5,623 ms` (p95 `12,002 ms`) |
| T3 Visual Overlay | Deterministic Pillow (model bbox) | `backend/services/overlay.py:render_model_bbox_overlay` | Draws only model-returned bbox + SOP spec on native image resolution. | No box if no bbox / `NO_DEFECT_FOUND` | `43 ms` (p95 `46 ms`) |
| T4 Floor Co-Pilot | `gemini-3.8-live` (WS `/api/live-copilot`) | `backend/services/model_router.py:run_tier4_live_copilot` | Bidirectional audio + transcript in EN / हिन्दी / मराठी for gloved operators. | `gemini-3.1-flash-lite` text + device TTS (`REST /api/copilot/chat`) | Measured per turn |
| Work-Order Extraction | `gemini-3.1-flash-lite` | `backend/db/demo_store.py:create_work_order` | Extracts `part_code`, `shift_priority`, `required_spares`, `sla_risk` from EN/HI/MR notes. | `FALLBACK_RULES` regex | Measured per WO |

---

## Measured Evaluation Results

> Measured on simulated inputs generated by backend/mock_rig (organiser-approved, no hardware). Not field accuracy.

- **Samples evaluated:** `18 / 18` balanced across PCB, CNC, and WELD (`7` true defects, `11` nominal/hard negatives, `0` errors)
- **True-defect recall:** `100.0%` (`7/7`, false negatives: `[]`)
- **False-escalation rate (nominal / hard negatives):** `100.0%` during this run because free-tier `gemma-4-26b-a4b-it` / `gemini-3.1-flash-lite` hit `503 UNAVAILABLE` / `5 s` timeouts on `15/18` calls and our **fail-safe gate** escalated unavailable visual checks to human review (see `eval/RESULTS.md` fallback breakdown)
- **Tier-2 defect-type agreement (on escalated true defects):** `6/7 (85.7%)`
- **SOP-guard unverified numeric values:** `0`
- **Measured latencies (p50 / p95):** T1-A DSP `0 / 10 ms`, T1-B Visual Gate `4,933 / 8,053 ms`, T2 Diagnosis `5,623 / 12,002 ms`, T3 Overlay `43 / 46 ms`, End-to-End `16,213 / 20,652 ms`
- **Measured token accounting (`N=18`, batch defect rate `38.9%`):** Gated `37,064` tokens vs estimated cloud-only `63,702` tokens (`18 × 3,539` mean T2 tokens) → `41.8%` measured token saving at this batch defect rate (real plant savings depend on the plant's actual defect rate and live API availability).

Full run artifacts: [eval/RESULTS.md](eval/RESULTS.md) and [eval/model_selection.md](eval/model_selection.md).

---

## Problem, Assumptions & Customer Evidence

- **Physical & economic assumptions:** Every constant (ISO 20816-3:2022 Group 2 zones, representative 7014C-class bearing geometry, SAC305 reflow window, AWS D8.8-style MIG porosity criteria, and unvalidated INR unit/downtime assumptions) is documented in [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).
- **Customer validation:** Not yet done; planned with Tier-2/3 automotive component suppliers in the Pune (Chakan / Bhosari) industrial belt. See [docs/CUSTOMER_EVIDENCE.md](docs/CUSTOMER_EVIDENCE.md).

---

## Competitive Landscape

| Competitor | Neutral Summary | Reference |
| --- | --- | --- |
| **Infinite Uptime** (Pune) | Industrial vibration hardware & predictive maintenance analytics for rotating equipment. | https://www.infinite-uptime.com |
| **Altizon** (Pune) | Industrial IIoT platform (Datonis) for factory telemetry, OEE, and condition monitoring. | https://altizon.com |
| **Tractian** | Wireless vibration/energy sensors paired with predictive maintenance and CMMS software. | https://tractian.com |
| **Augury** | Dedicated machine-health sensors and AI diagnostics for rotating industrial assets. | https://www.augury.com |
| **Nanoprecise** | Cellular IoT vibration/acoustic/temperature sensors for automated rotating-asset diagnostics. | https://nanoprecise.io |
| **Landing AI (LandingLens)** | Domain-specific computer vision platform for visual defect inspection. | https://landing.ai |
| **Google Cloud Visual Inspection AI** | Managed Google Cloud vision models for automated optical assembly inspection. | https://cloud.google.com/solutions/visual-inspection-ai |
| **Siemens Senseye / Industrial Copilot** | Enterprise predictive maintenance analytics and generative shop-floor assistant integrated with Siemens automation. | https://www.sw.siemens.com |

**Built differentiators in Vinyas:**
1. Closed shop-floor loop: multi-modal gating (DSP + vision) → SOP-guarded steps in English, Hindi, or Marathi → mandatory human disposition → multilingual work-order extraction.
2. Transparent per-stage provenance and measured edge-gate token accounting (`POST /api/line-run` and `eval/RESULTS.md`).
3. Multi-modality per line (vibration-led for internal CNC bearings; optical + process telemetry for PCB and MIG weld).

**Honest defensibility:** The prompt templates and UI are easy to copy. Real defensibility over time would come from labelled plant failure-event datasets collected during pilots, plant-specific SOP libraries, and distribution through regional CNC/SMT tooling distributors — none of which exist yet.

---

## Limitations (Honest List)
- **Simulated inputs only:** No physical camera or accelerometer is connected (`backend/mock_rig/`).
- **Demo SQLite storage:** Incidents, dispositions, and work orders reset whenever Cloud Run restarts a container (`infra/alloydb_schema.sql` is design-only).
- **API availability & quota:** Free-tier Gemini API experienced `503 UNAVAILABLE` spikes on newer preview models during testing; all 4 Nano Banana image models returned `429 RESOURCE_EXHAUSTED`, so generative Tier-3 images are omitted.
- **Voice input browser support:** Web Speech API (`SpeechRecognition`) requires Chrome/Edge; unsupported browsers prompt the operator to type instead.
- **Unvalidated economics & no customer interviews yet:** INR avoidable-loss figures are unvalidated team assumptions (`docs/ASSUMPTIONS.md`).

---

## Roadmap (Future Work — Not Shipped)
- Non-invasive no-PLC retrofit kit (USB accelerometer + industrial camera + on-prem Gemma edge node).
- Managed PostgreSQL / AlloyDB deployment using `infra/alloydb_schema.sql` (`vector(768)`).
- Streaming 16 kHz microphone PCM directly into `gemini-3.8-live` over `/api/live-copilot`.
- Pilot validation with Pune Chakan/Bhosari Tier-2/3 suppliers and tooling-distributor channel.

---

## Optional On-Prem Edge Client (Not Part of Hosted Demo)
`edge_client/edge_gateway.py` demonstrates running `backend/dsp/envelope.py` + a local Ollama Gemma model (`gemma4:e4b`) on an on-prem edge box and escalating only flagged parts to Cloud Run `/api/inspect`. It requires a local Ollama server and is **not** executed in the hosted Cloud Run demo.

---

## Run Locally & Deploy

```bash
# 1. Install dependencies & build frontend
pip install -r requirements.txt
cd frontend && npm ci && npm run build && cd ..

# 2. Run fast offline test suite (<2 s, no API key needed)
pytest -v

# 3. Run locally (set GEMINI_API_KEY in .env)
uvicorn backend.main:app --host 0.0.0.0 --port 8080

# 4. Deploy to Cloud Run (uses Secret Manager `gemini-api-key:latest`)
bash scripts/deploy_cloud_run.sh
```
