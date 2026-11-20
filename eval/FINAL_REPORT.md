# Vinyas — Final Engineering Report (`eval/FINAL_REPORT.md`)

**Branch:** `improve/jury-fixes`
**Date:** 2026-11-20

## 1. Phases Completed, Dropped & Moved to Limitations
- **Completed:**
  - **Phase 0 (Security hotfix):** Fixed SPA path traversal (`unquote` + `is_relative_to`), restricted asset serving, tightened CORS (`allow_credentials=False`), added per-IP token-bucket rate limiter (`30 req / 10 min`, HTTP 429), updated `scripts/deploy_cloud_run.sh` to Secret Manager (`--set-secrets=GEMINI_API_KEY=gemini-api-key:latest`).
  - **Phase 1 (Truthful provenance):** Added `ModelAttempt`, `StageProvenance`, JSON attempt logging, `/api/metrics`, deleted shared `last_inference_mode`, removed all latency padding and banned claims (`SynthID`, `95.4%`, `<50 ms`, `AlloyDB Express` runtime, `Tata Motors`).
  - **Phase 2 (Mock Rig v2):** Built `backend/mock_rig/` (60 seeded samples, 20/line, computed `BPFO ≈ 793 Hz` at `5400 rpm`, zero text on images verified via `eval/mock_rig_contact_sheet.png`, hidden `manifest.json` isolated from inference, blind draw + post-inspection reveal).
  - **Phase 3 (Real Tier-1 gate):** Built `backend/dsp/envelope.py` (2–8 kHz Butterworth → Hilbert envelope → FFT → BPFO/2×BPFO SNR, kurtosis wrench-strike rejection, ISO 20816-3 reference zones, envelope spectrum PNG) + `gemma-4-26b-a4b-it` T1-B visual gate + fail-safe combiner (`backend/services/gate.py`). Rewrote `edge_client/edge_gateway.py` with no `LINE_D_HEALTHY` short-circuit.
  - **Phase 4 (Tier-2/3/4, Guard, Economics):** Benchmarked 6 models in `eval/model_selection.md` (`gemini-3.1-flash-lite` primary, hedged with `gemini-3.8-flash`; `gemini-4-hydrogen` dropped after `0/8` 503/timeouts). Added `sop_guard.py`, deterministic `economics.py` (`₹0` nominal), model-bbox-only `overlay.py` (deleted `bbox_by_scenario`), and `gemini-3.8-live` audio+transcript over `WS /api/live-copilot`.
  - **Phase 5 (Retrieval, Disposition, WO Extraction, Storage Honesty):** Expanded to 18 SOPs with `gemini-embedding-2` (`768-D`) cosine retrieval + labelled keyword fallback; added `POST /api/incidents/{id}/disposition` gating work orders; added multilingual Gemini work-order extraction; moved production schema to `infra/alloydb_schema.sql` (no `array_fill` constant vectors).
  - **Phase 6 (Eval harness & Line Run):** Built `scripts/eval_pipeline.py` and `POST /api/line-run`, generated `eval/RESULTS.md` and `eval/results.json`.
  - **Phase 7 (Operator & Engineer UX):** Rebuilt `frontend/src/App.jsx` + `frontend/src/i18n.js` (EN / हिन्दी / मराठी, Operator/Engineer views, zero font `< 12 px`, zero `?? <number>` defaults, aria-labels, `aria-live`, WebSocket co-pilot + audio playback, disposition panel, session tally). Built cleanly (`vite build` in `635 ms`).
  - **Phase 8 (Repo hygiene & offline tests):** Deleted 9,276 lines of dead legacy code, pinned Python 3.11 dependencies in `requirements.txt`, updated `Dockerfile` and `scripts/provision_gcp.sh`. **24/24 offline tests pass in `1.13 s`**; live smoke test separated in `tests/live/test_live_smoke.py`.
  - **Phase 9 (Docs, Claims, Deck, Script):** Rewrote `README.md`, created `docs/ASSUMPTIONS.md`, `docs/CUSTOMER_EVIDENCE.md`, `docs/JURY_QA.md`, `docs/DECK_OUTLINE.md`, `docs/DEMO_SCRIPT.md`, `eval/claim_audit.md`.
- **Dropped / Moved to Limitations (with reason):**
  - **Tier-3 async Nano Banana image generation (P1):** Dropped because all 4 Nano Banana image models (`gemini-nano-banana-2.1`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image`, `gemini-3-pro-image`) returned `429 RESOURCE_EXHAUSTED` (no quota on this key). Shipped deterministic Pillow overlay of the model's real `bbox` instead, with zero Nano Banana runtime claims.
  - **Firestore persistence (P2):** Omitted to avoid creating unapproved GCP resources; SQLite demo store is labelled honestly (`Demo store — resets when the server restarts`).
  - **Live Cloud Run deploy & live verification (Phase 10):** Ready to run (`scripts/deploy_cloud_run.sh` + `scripts/verify_live.py`), awaiting user approval to deploy and confirmation that `gemini-api-key` is added to Secret Manager.

## 2. Before / After Comparison

| Probe | Baseline (Pre-Fix, §2.3) | After Fixes (Measured Local / Verified Code) |
| --- | --- | --- |
| Path traversal (`..%2f..%2fetc%2fos-release`) | Arbitrary file read | Blocked (`404` / never leaks files; `tests/test_security.py`) |
| API key storage | Plain `--set-env-vars` | Secret Manager `--set-secrets=GEMINI_API_KEY=gemini-api-key:latest` |
| Tier-1 verdict logic | Scenario name (`LINE_D_HEALTHY` hard-coded) | Deterministic DSP (`0 ms` p50) + `gemma-4-26b-a4b-it` visual gate (fail-safe) |
| Mock images | Text naming defect + scenario key + `SynthID` footer | Zero text (`eval/mock_rig_contact_sheet.png`), hidden `manifest.json` |
| Tier-2 primary model | Mislabelled `gemini-4-hydrogen (Live via 3.1-flash-lite)` | Benchmark-selected `gemini-3.1-flash-lite` hedged with `gemini-3.8-flash` |
| Tier-3 visual card | Fixed `bbox_by_scenario` labelled `Nano Banana SynthID` | Deterministic overlay of model `bbox` only (no box on `NO_DEFECT_FOUND`) |
| SOP retrieval | Hash bag-of-words + forced `max(sim, 0.96)` | `gemini-embedding-2` (`768-D`) over 18 SOPs + labelled keyword fallback |
| Economics | LLM prompt `integer > 25000` | Deterministic `economics.py` (`docs/ASSUMPTIONS.md`), `₹0` nominal |
| Human approval | None | Mandatory QE/Supervisor disposition before work order |
| Offline test suite | 7/7 in `180 s` (live API, scripted assertions) | 24/24 in `1.13 s` (offline, zero scripted verdict assertions) |

## 3. Eval Headline Numbers (from `eval/RESULTS.md`)

> Measured on simulated inputs generated by backend/mock_rig (organiser-approved, no hardware). Not field accuracy.

- **Samples:** `18 / 18` (`0` errors)
- **True-defect recall:** `100.0%` (`7/7`, false negatives: `[]`)
- **False-escalation rate (nominal / hard negatives):** `100.0%` (driven by `15/18` free-tier API `503`/timeout events triggering fail-safe escalation)
- **Tier-2 defect-type agreement:** `6/7 (85.7%)`
- **SOP-guard unverified values:** `0`
- **Measured latencies (p50 / p95):** T1-A `0 / 10 ms`, T1-B `4,933 / 8,053 ms`, T2 `5,623 / 12,002 ms`, T3 `43 / 46 ms`, End-to-End `16,213 / 20,652 ms`
- **Measured token accounting (`N=18`, `38.9%` defect rate):** `37,064` gated tokens vs `63,702` cloud-only (`41.8%` saving at this batch defect rate)

## 4. Model Routing Decision & Benchmark (`eval/model_selection.md`)

| Model ID | Success | Schema Valid | Defect Agreement | p50 (ms) | p95 (ms) |
| --- | --- | --- | --- | ---: | ---: |
| `gemini-4-hydrogen` | `0/8` | `0/8` | `0/8` | 9,938 | 15,548 |
| `gemini-3.8-flash` | `0/8` | `0/8` | `0/8` | 5,448 | 14,286 |
| `gemini-3.5-flash` | `0/8` | `0/8` | `0/8` | 14,800 | 15,013 |
| `gemini-3.1-flash-lite` | `3/8` | `3/8` | `3/8` | 6,367 | 12,721 |
| `gemini-2.5-flash` | `0/8` (`404`) | `0/8` | `0/8` | 612 | 963 |
| `gemini-2.5-flash-lite` | `0/8` (`404`) | `0/8` | `0/8` | 584 | 868 |

**Decision:** Primary `gemini-3.1-flash-lite`, hedged runner-up `gemini-3.8-flash` (trigger at `6.0 s`).

## 5. User Actions Still Required
1. **Rotate `GEMINI_API_KEY`** in Google AI Studio (restrict to Generative Language API) and upload it to Secret Manager (`gemini-api-key:latest`).
2. **Approve Cloud Run deploy (Phase 10)** so we can run `scripts/deploy_cloud_run.sh`, `scripts/verify_live.py`, and `scripts/eval_pipeline.py --target live --n 30`.
3. **Billing decision:** Decide whether to enable billing / paid quota to reduce `503 UNAVAILABLE` spikes and unlock Nano Banana image models (currently omitted cleanly).
4. **Record 3:00 demo video** following `docs/DEMO_SCRIPT.md` against the deployed Cloud Run URL.
5. **Customer evidence:** Fill `docs/CUSTOMER_EVIDENCE.md` if any plant interviews are conducted before submission (otherwise keep the honest "not yet done" statement).
6. **Merge & push approval:** Approve merging `improve/jury-fixes` into `main` and pushing after Phase 10 live verification.

## 6. Open Risks for Judging Day
- **Free-tier Gemini API `503 UNAVAILABLE` spikes:** Observed heavily during benchmarking; fail-safe escalation keeps recall at 100% but increases false escalations and latency when models 503. Paid quota / Vertex AI is the cleanest mitigation.
- **Cloud Run cold starts & SQLite reset:** `--min-instances=1` reduces cold starts, but container recycles reset demo SQLite data (labelled honestly in UI).
- **Rate limit (`30 req / 10 min` per IP):** Sufficient for judges, but rapid automated testing from one shared Wi-Fi NAT could hit HTTP 429.
- **Browser speech support:** `SpeechRecognition` requires Chrome/Edge; Safari/Firefox operators must type (UI handles this cleanly).

## 7. Harsh Self-Score Against Jury Rubric

| Criterion (Weight) | Score | Evidence |
| --- | ---: | --- |
| Functional product (30%) | **23 / 30** | Blind mock rig, real Hilbert DSP, model-bbox overlay, disposition-gated work orders, WebSocket co-pilot, and 24/24 offline tests work end-to-end; deducted for live deploy pending user approval and high false-escalation rate under free-tier 503 load. |
| Technical architecture (20%) | **17 / 20** | Clean separation of DSP, fail-safe gate, hedged routing, SOP numeric guard, deterministic economics, Secret Manager deploy, and 9,276 lines of dead code removed; deducted for SQLite demo store instead of managed DB. |
| Google AI integration depth (20%) | **15 / 20** | Real non-overlapping use of `gemma-4-26b-a4b-it`, `gemini-3.1-flash-lite`, `gemini-embedding-2`, and `gemini-3.8-live` (audio+transcript) with full provenance; deducted because Nano Banana had no quota and 503s forced frequent fallbacks during eval. |
| Problem–solution fit (15%) | **9 / 15** | Technically grounded domain physics (ISO 20816-3, computed BPFO, IPC-A-610, AWS D8.8) and human-in-the-loop disposition; deducted because no real customer interviews or plant validation exist yet. |
| UX / accessibility (10%) | **9 / 10** | Operator/Engineer views, EN/हिन्दी/मराठी, `>=12px` typography, `aria-live`, `aria-label`, big PTT button, zero jargon in Operator view; minor deduction for Chrome-only speech-in. |
| Innovation (5%) | **4 / 5** | Closed loop (DSP + vision → SOP-guarded vernacular guidance → human disposition → multilingual WO) with honest token accounting and provenance. |
| **Total** | **77 / 100** | Up from **35.5 / 100** baseline; honest, reproducible, zero fake claims. |
