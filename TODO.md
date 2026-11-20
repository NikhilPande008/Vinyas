# OpsSense AI — Sequential Build & Verification Tracker (`TODO.md`)

**Project:** OpsSense AI ("Autonomous Edge-to-Cloud Quality & Maintenance Twin for Discrete Manufacturing")  
**Hackathon:** Startup Buildathon India (Pune City Buildathon)  
**Workflow Rule:** Strict Gate-by-Gate execution.

---

## [x] Gate 0: Plan Gate (Workspace Discovery & Architecture Blueprint)
- [x] Inspect workspace directory, existing files, and local CLI tools (`python3`, `node`, `npm`, `gcloud`, `docker`).
- [x] Generate `implementation_plan.md` covering repository tree, `.agents/skills/` specification, AlloyDB Express (PostgreSQL 18) ScaNN + `AI.EXTRACT()`/`AI.IF()` schema, Google AI Model Routing, and REST/WebSocket API contracts.
- [x] Generate `TODO.md` tracking all sequential gates.
- [x] Provision GCP Billing (`016344-D7A282-081BCC`), Project (`vinyas-buildathon-6626`), APIs, and restricted `GEMINI_API_KEY` into `.env`.

---

## [x] Gate 1: Step 1 — Database, Agent Skills & Backend Core
- [x] Create Authentic Google Agent Skills under `/.agents/skills/` (`agentskills.io` spec):
  - [x] `/.agents/skills/ops-db-guardrails/SKILL.md`
  - [x] `/.agents/skills/pcb-defect-triage/SKILL.md` + `references/ipc_solder_standards.md`
  - [x] `/.agents/skills/bearing-acoustic-diagnostics/SKILL.md` + `references/vibration_thresholds.md`
  - [x] `/.agents/skills/maintenance-work-order/SKILL.md` + `scripts/calc_downtime_cost.py`
- [x] Create `backend/config.py` (Pydantic Settings reading `GEMINI_API_KEY`, `GOOGLE_CLOUD_PROJECT`, `ALLOYDB_DSN`, `GCS_BUCKET`, `DEMO_FALLBACK_ENABLED` with zero hardcoded keys).
- [x] Create `backend/schemas.py` (`InspectionRequest`, `Tier1TriageResult`, `Tier2DiagnosisResult`, `WorkOrderCreate`, `WorkOrderRecord`, `TelemetryMetrics`, `InspectionResponse`).
- [x] Create `backend/db/init_alloydb.sql` (PostgreSQL 18 DDL with `vector`, `alloydb_scann`, `google_ml_integration`, `equipment_sops`, `inspection_incidents`, `work_orders`, ScaNN cosine index, and 6 Pune manufacturing SOP rows).
- [x] Create `backend/db/alloydb_service.py` (Async PostgreSQL connector with ScaNN vector search, `AI.EXTRACT()` + `AI.IF()` in-SQL enrichment with Python fallback, and zero-crash local SQLite fallback `opssense_local.db`).
- [x] Create `backend/services/skill_loader.py` (Progressive Disclosure loader: startup YAML metadata index + dynamic domain skill & reference loading + SQL guardrail validator).
- [x] Create `backend/services/simulator_assets.py` (Serves 4 Pune discrete manufacturing scenarios with high-res inspection images + WAV audio telemetry for Line B).
- [x] Create `backend/services/model_router.py` (Official `google-genai` SDK integration for Tier-1 `gemini-3.5-flash-lite`, Tier-2 `gemini-4-hydrogen` / `gemini-3.8-flash`, Tier-3 `gemini-nano-banana-2.1` + Pillow callout overlay fallback, Tier-4 `gemini-3.8-live` + flash streaming fallback, and deterministic cached JSON circuit breakers).
- [x] Create `backend/main.py` (FastAPI app on port 8080 with `/health`, `/api/scenarios`, `/api/skills`, `/api/inspect`, `/api/work-orders`, `/api/copilot/chat`, WebSocket `/api/live-copilot`, and static mount for `/frontend/dist`).
- [x] Create `edge_client/edge_gateway.py` (Standalone `gemma4:e4b` local Ollama multimodal pre-screener that escalates anomalies to `/api/inspect`).
- [x] **Gate 1 Verification:** `pytest -v` passed (7/7 tests passing).

---

## [x] Gate 2: Step 2 — Frontend Control Room & Virtual Factory Simulator
- [x] Initialize `/frontend` with React 18, Vite, Tailwind CSS, and `lucide-react`.
- [x] Build **Top Telemetry Bar** (`OpsSense AI // Autonomous Edge-to-Cloud Quality Twin`, live `/health` status pills for Cloud Run, AlloyDB Express + ScaNN, Inference Mode, and **"AI Stack & Architecture"** modal button).
- [x] Build **"AI Stack & Architecture" Modal** showing Model-to-Role table, `.agents/skills/` Progressive Disclosure status, and stage latency metrics (`tier1_ms`, `scann_rag_ms`, `tier2_ms`, `tier3_ms`).
- [x] Build **Left Column — Virtual Factory Line Simulator** (4 clickable scenarios, image preview, sensor cards, playable audio clip for Line B, Webcam/Upload override toggle, and **"Run Edge-to-Cloud Inspection"** CTA).
- [x] Build **Center Column — Agentic Pipeline, ScaNN Grounding & Visual SOP** (5-stage stepper, Diagnosis Summary Card, Side-by-side Raw vs. Nano Banana 2.1 Visual Repair Overlay, and **"Approve & Log Work Order to AlloyDB"** button).
- [x] Build **Right Column — Gemini Live Co-Pilot & Persisted AlloyDB Incident Log** (Voice PTT mic + quick prompt chips + streaming response, and Persisted Work Orders ledger displaying `AI.EXTRACT()` tags and `AI.IF()` SLA flags).
- [x] **Gate 2 Verification:** `npm run build` compiled `/frontend/dist` cleanly with zero errors.

---

## [x] Gate 3: Step 3 — Single-Container Docker & Cloud Run Deployment
- [x] Create multi-stage `Dockerfile` (Stage 1: Node 20 builds `/frontend/dist`; Stage 2: Python 3.11-slim serves FastAPI + `/frontend/dist` via Uvicorn on port `8080`).
- [x] Update `.dockerignore`, `requirements.txt`, and `scripts/deploy_cloud_run.sh`.
- [x] Deploy single container live to Google Cloud Run (`--allow-unauthenticated`, port `8080`, region `asia-south1`).

---

## [x] Gate 4: Step 4 — Hardening, Security & AI-Evaluation Docs
- [x] Verify circuit-breaker fallbacks across Tier-1, Tier-2, Tier-3, Tier-4, and Tier-5 (`AI.EXTRACT()` / `AI.IF()`).
- [x] Verify `.gitignore` and `.dockerignore` block `.env`, `secrets/`, `*.json` keys, `__pycache__/`, `node_modules/`, and `*.db`.
- [x] Write AI-Evaluation-ready `README.md` with quantified problem statement, Mermaid architecture diagram, Model Justification Matrix, Virtual Simulator vs. Edge Client guide, and `gcloud run deploy` commands.
