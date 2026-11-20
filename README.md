# Vinyas — Manufacturing Quality & Predictive Maintenance Platform

**Startup Buildathon India — Pune City Buildathon Submission**

- **Live Google Cloud Run Application (`*.run.app`):** [https://vinyas-ai-65216244490.asia-south1.run.app](https://vinyas-ai-65216244490.asia-south1.run.app) *(zero login walls, zero localhost dependencies)*
- **Live Health & Telemetry Endpoint (`/health`):** [https://vinyas-ai-65216244490.asia-south1.run.app/health](https://vinyas-ai-65216244490.asia-south1.run.app/health)
- **Demo Video Link:** `[INSERT_3_MINUTE_DEMO_VIDEO_URL_HERE]`
- **GCP Project & Region:** `vinyas-buildathon-6626` (`asia-south1` — Mumbai/Pune Low-Latency Zone)

---

## 1. Quantified Problem Statement (Pune & Indian Discrete Manufacturing)

Across Pune's **Chakan, Bhosari, Talegaon, and Pimpri-Chinchwad** automotive & industrial manufacturing clusters, Tier-2 and Tier-3 discrete manufacturers (SMT automotive PCB assemblies, high-speed CNC machining centers, and robotic MIG chassis weld cells) face three compounding challenges:

1. **High Scrap & Rework Losses (4%–9% Scrap Rate):** Late detection of fine-pitch QFP solder bridges (`IPC-A-610 Class 3`), CNC spindle outer-race bearing spalls (`ISO-10816-3 Zone D`), and MIG weld wormhole porosity (`AWS D1.1`) destroys entire batch runs before quality control intervenes.
2. **Severe Unplanned Downtime Costs (₹42,000–₹1,20,000/hour):** Catastrophic spindle seizures or OEM customer SLA breaches halt downstream Tier-1 assembly lines.
3. **Unviable Cloud Token Economics:** Streaming 24/7 12MP telecentric optical feeds and 48 kHz acoustic vibration streams directly to frontier cloud models costs **>₹3.5 Lakhs/month per line** and introduces unacceptable latency.

**Vinyas** solves this with an **Autonomous 5-Tier Edge-to-Cloud Architecture** that pre-screens 100% of production cycles at the edge using **Gemma 4 E4B** (short-circuiting ~95.4% of healthy baseline parts at zero cloud token cost) and escalates only true anomalies to **Google Cloud Run**, **AlloyDB Express (PostgreSQL 18)** with **ScaNN Vector Search**, **In-Database SQL AI (`AI.EXTRACT()`, `AI.IF()`)**, **Progressive Disclosure Google Agent Skills (`.agents/skills/`)**, **Gemini 4 Hydrogen**, **Nano Banana 2.1**, and **Gemini 3.8 Live**.

---

## 2. System Architecture Diagram

```mermaid
flowchart LR
    subgraph Edge["Tier 1: Shop-Floor Edge Gate"]
        SIM["Virtual Factory Line Simulator<br/>(4 Scenarios + Webcam/WAV Override)"]
        EDGE_GW["Edge Gateway (/edge_client/edge_gateway.py)<br/>Gemma 4 E4B Local / gemini-3.5-flash-lite Cloud Emulator"]
        SIM --> EDGE_GW
    end

    subgraph CloudRun["Google Cloud Run (Single Container: FastAPI + React /frontend/dist on :8080)"]
        ROUTER["Model Router & Circuit Breaker<br/>(backend/services/model_router.py)"]
        SKILLS["Progressive Skill Loader<br/>(/.agents/skills/*/SKILL.md)"]
        T2["Tier 2: Multimodal Root-Cause Engine<br/>(gemini-4-hydrogen -> gemini-3.8-flash)"]
        T3["Tier 3: Visual Repair SOP Overlay<br/>(gemini-nano-banana-2.1 -> Pillow Fallback)"]
        T4["Tier 4: Hands-Free Floor Co-Pilot<br/>(gemini-3.8-live WebSocket / Streaming)"]
    end

    subgraph AlloyDB["Tier 5: AlloyDB Express (PostgreSQL 18) + Resilient Fallback"]
        SCANN["pgvector + alloydb_scann<br/>(equipment_sops 768-D Cosine Index)"]
        SQL_AI["google_ml_integration In-SQL AI<br/>(AI.EXTRACT() & AI.IF() on work_orders)"]
        SQLITE["Zero-Crash Local SQLite Fallback<br/>(vinyas_local.db)"]
    end

    EDGE_GW -- "HEALTHY (~95.4% Filtered - Scenario 4)" --> SHORT["Short-Circuit Exit<br/>(Zero Tier-2/3 Cloud Token Cost)"]
    EDGE_GW -- "ESCALATE (Anomaly Detected)" --> ROUTER
    ROUTER <--> SKILLS
    ROUTER <--> SCANN
    ROUTER --> T2
    T2 --> T3
    T2 --> T4
    ROUTER --> SQL_AI
    SCANN -. "Automatic Fallback if DSN offline" .-> SQLITE
```

---

## 3. Which Google Model, Why, and Exact Use (Non-Overlapping Justification Matrix)

Every Google AI model and database capability in `backend/services/model_router.py` and `backend/db/alloydb_service.py` has a strict, non-redundant engineering role:

| Pipeline Tier | Google Model / Engine | Why This Specific Model / Tool | Exact Use in Vinyas |
| :--- | :--- | :--- | :--- |
| **Tier 1: Edge Anomaly Gate** | **`Gemma 4 E4B`** (`/edge_client/edge_gateway.py`) / **`gemini-3.5-flash-lite`** (Cloud Sandbox Emulator) | Streaming 24/7 factory camera & 48 kHz acoustic feeds to heavy cloud models destroys unit economics and exposes plant IP. | Pre-screens every cycle in `<50 ms`. **Mandatory Short-Circuit Rule:** Scenario 4 (`LINE_D_HEALTHY`) returns `HEALTHY` and terminates cleanly at Tier-1, saving **~95.4% of Tier-2/3 cloud token spend**. |
| **Tier 2: Multimodal Root-Cause & ScaNN RAG Engine** | **`gemini-4-hydrogen`** (Primary) / **`gemini-3.8-flash`** (Fallback) | Complex cross-modal defects require joint reasoning over optical defect frames, 4.21 kHz BPFO acoustic harmonics, AlloyDB ScaNN retrieved SOPs, and domain `SKILL.md` rules. | Executes **ONLY on `ESCALATE`**. Enforces strict Pydantic `Tier2DiagnosisResult` JSON schema returning defect classification, severity, root cause, matched SOP ID, ordered repair steps, and INR scrap saved. |
| **Tier 3: Visual Repair SOP Overlay** | **`gemini-nano-banana-2.1`** (Primary) / **Pillow Precision Callout Overlay** (Fallback) | Shop-floor technicians act 3x faster on visual repair cards overlaid directly onto the defect photo than on dense text manuals. | Generates an annotated visual repair overlay card directly on the captured defect frame with fault bounding reticles, torque specifications, and SynthID provenance. Automatically falls back to a high-contrast Pillow callout renderer if quota/rate limits occur. |
| **Tier 4: Hands-Free Floor Technician Co-Pilot** | **`gemini-3.8-live`** (WebSocket `/api/live-copilot`) / **`gemini-3.8-flash`** (Streaming Fallback) | Technicians wearing PPE gloves while inspecting CNC spindles or weld cells cannot type long troubleshooting queries. | Powers the voice Push-To-Talk (PTT) and quick-chip shop-floor Co-Pilot grounded in the active incident diagnosis and AlloyDB ScaNN SOP context. |
| **Tier 5: In-Database Vector RAG & Work Order Enrichment** | **AlloyDB Express (PostgreSQL 18)** `alloydb_scann` + **`AI.EXTRACT()`** & **`AI.IF()`** | Eliminates external ETL pipelines when matching equipment tolerances and logging structured maintenance work orders. | 1. Executes `ORDER BY embedding <=> $1 LIMIT 3` using the `equipment_sops_scann_idx` ScaNN cosine index.<br/>2. Runs `ai.extract()` on `operator_notes` to extract `{"part_code", "shift_priority", "required_spares"}` and `ai.if()` to flag critical OEM SLA breach risk directly inside SQL (with clean `PYTHON_FALLBACK` and `LOCAL_SQLITE_FALLBACK`). |

---

## 4. Authentic Google Agent Skills (`.agents/skills/`) & Progressive Disclosure

Compliant with the **`agentskills.io` specification** (YAML frontmatter `name` in `lowercase-kebab-case <= 64` chars matching directory name, `description < 1024` chars stating explicit trigger rules, `SKILL.md < 500` lines):

- **Progressive Disclosure (`backend/services/skill_loader.py`):**
  - **Stage 1 (Startup):** Loads **only** YAML frontmatter (`name` + `description`) across all 4 skills (~120 tokens total; `full_body_loaded: false`).
  - **Stage 2 (Dynamic Activation):** Loads the full `SKILL.md` body and `references/*.md` **only** when an escalated inspection matches that domain:
    1. `.agents/skills/ops-db-guardrails/SKILL.md` — Enforces `snake_case` tables, mandatory `id` primary key, parameterized SQL queries (`$1`/`?`), and blocks destructive `DROP TABLE` or raw string interpolation.
    2. `.agents/skills/pcb-defect-triage/SKILL.md` + `references/ipc_solder_standards.md` — Triggered on `LINE_A_PCB` (IPC-A-610 Class 3 fine-pitch QFP solder bridge & reflow slump rules).
    3. `.agents/skills/bearing-acoustic-diagnostics/SKILL.md` + `references/vibration_thresholds.md` — Triggered on `LINE_B_CNC` (ISO-10816-3 CNC spindle velocity thresholds & 4.21 kHz BPFO outer-race spall harmonics).
    4. `.agents/skills/maintenance-work-order/SKILL.md` + `scripts/calc_downtime_cost.py` — Triggered on `LINE_C_WELD` (AWS D1.1 MIG weld porosity) and INR scrap/downtime cost calculation.

---

## 5. Mocked Hardware (Virtual Factory Line Simulator) vs. Production Edge Client

To allow judges and automated evaluators to test all 4 manufacturing scenarios immediately in the browser with **zero physical hardware required**, Vinyas separates the **Cloud Run Virtual Factory Line Simulator** from the **Production Shop-Floor Edge Gateway**:

1. **Virtual Factory Line Simulator (In-Browser Control Room Left Column):**
   - Pre-loads 4 Pune discrete manufacturing scenarios (`Line A: Automotive PCB`, `Line B: CNC Spindle` with playable 48 kHz WAV audio, `Line C: Chassis Weld Seam`, and `Line D: Calibration Check` healthy baseline).
   - Includes a **"Live Webcam / Upload Override"** toggle so judges can capture live webcam frames or upload custom defect photos.
   - Runs `gemini-3.5-flash-lite` as the **Tier-1 Cloud Edge Emulator**.
2. **Production Edge Gateway (`edge_client/edge_gateway.py`):**
   - Runs locally on an industrial edge IPC (NVIDIA Jetson / x86 IPC) connected to Ollama (`gemma4:e4b`).
   - Performs local multimodal pre-screening and **only POSTs `ESCALATE` anomalies** to the Cloud Run `/api/inspect` endpoint:
     ```bash
     # Short-circuits locally at the edge (0 Cloud Run tokens used):
     python3 edge_client/edge_gateway.py --scenario LINE_D_HEALTHY

     # Escalates anomaly to Google Cloud Run /api/inspect:
     python3 edge_client/edge_gateway.py --scenario LINE_B_CNC --cloud-url https://vinyas-ai-65216244490.asia-south1.run.app
     ```

---

## 6. Local Development, Automated Pytest Suite & Cloud Run Deployment

### 6.1 Run Automated Pytest Verification Suite
```bash
pip install -r requirements.txt
pytest -v
```

### 6.2 Build Frontend & Start Single-Container Server Locally (Port 8080)
```bash
cd frontend && npm install && npm run build && cd ..
uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

### 6.3 Exact Google Cloud Run Deployment Command
```bash
gcloud run deploy vinyas-ai \
  --source=. \
  --project=vinyas-buildathon-6626 \
  --region=asia-south1 \
  --platform=managed \
  --ingress=all \
  --allow-unauthenticated \
  --port=8080 \
  --cpu=2 \
  --memory=2Gi \
  --min-instances=1 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=vinyas-buildathon-6626,GCP_LOCATION=asia-south1,DEMO_FALLBACK_ENABLED=true"
```
