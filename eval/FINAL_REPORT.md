# Vinyas — Final Engineering Report (`eval/FINAL_REPORT.md`)

**Branch:** `improve/jury-fixes`
**Date:** 2026-11-20 (updated ~23:50 IST after the post-audit fix pass, commits `835e057` onward)

## 1. Phases Completed, Dropped & Moved to Limitations
- **Completed:**
  - **Phase 0 (Security hotfix):** Fixed SPA path traversal (`unquote` + `is_relative_to`), restricted asset serving, tightened CORS (`allow_credentials=False`), added per-IP token-bucket rate limiter (`30 req / 10 min`, HTTP 429), updated `scripts/deploy_cloud_run.sh` to Secret Manager (`--set-secrets=GEMINI_API_KEY=gemini-api-key:latest`).
  - **Phase 1 (Truthful provenance):** Added `ModelAttempt`, `StageProvenance`, JSON attempt logging, `/api/metrics`, deleted shared `last_inference_mode`, removed all latency padding and banned claims (`SynthID`, `95.4%`, `<50 ms`, `AlloyDB Express` runtime, `Tata Motors`).
  - **Phase 2 (Mock Rig v2):** Built `backend/mock_rig/` (60 seeded samples, 20/line, computed `BPFO ≈ 793 Hz` at `5400 rpm`, zero text on images verified via `eval/mock_rig_contact_sheet.png`, hidden `manifest.json` isolated from inference, blind draw + post-inspection reveal).
  - **Phase 3 (Real Tier-1 gate):** Built `backend/dsp/envelope.py` (2–8 kHz Butterworth → Hilbert envelope → FFT → BPFO/2×BPFO SNR, kurtosis wrench-strike rejection, ISO 20816-3 reference zones, envelope spectrum PNG) + `gemma-4-26b-a4b-it` T1-B visual gate (re-chosen by benchmark in the post-audit pass) + fail-safe combiner (`backend/services/gate.py`). Rewrote `edge_client/edge_gateway.py` with no `LINE_D_HEALTHY` short-circuit.
  - **Phase 4 (Tier-2/3/4, Guard, Economics):** Benchmarked 6 models in `eval/model_selection_run1.md` (`gemini-3.1-flash-lite` primary, hedged with `gemini-3.8-flash`, later replaced by `gemini-3.5-flash-lite` in the post-audit pass; `gemini-4-hydrogen` dropped after `0/8` 503/timeouts). Added `sop_guard.py`, deterministic `economics.py` (`₹0` nominal), model-bbox-only `overlay.py` (deleted `bbox_by_scenario`), and `gemini-3.8-live` audio+transcript over `WS /api/live-copilot`.
  - **Phase 5 (Retrieval, Disposition, WO Extraction, Storage Honesty):** Expanded to 18 SOPs with `gemini-embedding-2` (`768-D`) cosine retrieval + labelled keyword fallback; added `POST /api/incidents/{id}/disposition` gating work orders; added multilingual Gemini work-order extraction; moved production schema to `infra/alloydb_schema.sql` (no `array_fill` constant vectors).
  - **Phase 6 (Eval harness & Line Run):** Built `scripts/eval_pipeline.py` and `POST /api/line-run`, generated `eval/RESULTS.md` and `eval/results.json`.
  - **Phase 7 (Operator & Engineer UX):** Rebuilt `frontend/src/App.jsx` + `frontend/src/i18n.js` (EN / हिन्दी / मराठी, Operator/Engineer views, zero font `< 12 px`, zero `?? <number>` defaults, aria-labels, `aria-live`, WebSocket co-pilot + audio playback, disposition panel, session tally). Built cleanly (`vite build` in `635 ms`).
  - **Phase 8 (Repo hygiene & offline tests):** Deleted 9,276 lines of dead legacy code, pinned Python 3.11 dependencies in `requirements.txt`, updated `Dockerfile` and `scripts/provision_gcp.sh`. **24/24 offline tests pass in `1.13 s`**; live smoke test separated in `tests/live/test_live_smoke.py`.
  - **Phase 9 (Docs, Claims, Deck, Script):** Rewrote `README.md`, created `docs/ASSUMPTIONS.md`, `docs/CUSTOMER_EVIDENCE.md`, `docs/JURY_QA.md`, `docs/DECK_OUTLINE.md`, `docs/DEMO_SCRIPT.md`, `eval/claim_audit.md`.
- **Dropped / Moved to Limitations (with reason):**
  - **Tier-3 async Nano Banana image generation (P1):** Dropped because all 4 Nano Banana image models (`gemini-nano-banana-2.1`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image`, `gemini-3-pro-image`) returned `429 RESOURCE_EXHAUSTED` (no quota on this key). Shipped deterministic Pillow overlay of the model's real `bbox` instead, with zero Nano Banana runtime claims.
  - **Firestore persistence (P2):** Omitted to avoid creating unapproved GCP resources; SQLite demo store is labelled honestly (`Demo store — resets when the server restarts`).
  - **Live Cloud Run deploy (Phase 10):** Done. Revision `vinyas-ai-00002-cw4` went live at 22:15 IST with the key from Secret Manager; `eval/live_verification.md` and `eval/security_check.md` record the live checks. The post-audit fixes below are **not deployed yet** (deploy awaits approval).

### Post-audit fix pass (after the Phase 10 live check)
The live check and a packet review found problems the earlier phases missed. Fixed and committed:
- **Upload false negative:** a solder-bridge upload passed as `HEALTHY` live. Cause: the visual models could not see the bridge, which was drawn as a flat white box the colour of the leads (all three models called it NOMINAL in a spot check). Bridges were redrawn as shiny solder at the lead feet (labels, seeds, telemetry unchanged; logged in `docs/MOCK_RIG.md`), the visual-gate prompt now inspects each region in turn, and the gate model was re-chosen by `eval/visual_gate_benchmark.md`.
- **Visual-gate availability:** the gate is now a staggered hedge (`gemini-3.5-flash-lite` → `gemma-4-26b-a4b-it` → `gemini-3.1-flash-lite`, next model after 3 s or on failure, 12 s cap). Gemma 4 had 100% accuracy on the frames it answered but answered only 34/46 on the free tier and is twice as slow, so it is the first backup rather than the primary.
- **Tier-2 runner-up:** `gemini-3.8-flash` returned `429` quota errors on every call; re-benchmarked (`eval/model_selection.md`, run 2) and replaced by `gemini-3.5-flash-lite`.
- **Token "saving" artifact:** the old 41.8% came from failed Tier-2 calls costing 0 tokens while every part escalated. `compute_gate_token_accounting` now charges each escalation the mean measured Tier-2 cost.
- **Money on rule holds:** rule-based Tier-2 fallbacks showed an avoidable-loss figure (e.g. ₹31,100 on a healthy part). They now show "Not estimated".
- **Threshold mismatch:** `SKILL.md` said BPFO SNR ≥ 6 dB while the code uses ≥ 14 dB (healthy spindles reach 10.5 dB from noise). Aligned, with `scripts/calibrate_dsp_gate.py` → `eval/dsp_gate_calibration.md` and a test that keeps them in sync.
- **Public eval token:** reveal-by-token is disabled on Cloud Run while the token is the public default.
- **Co-pilot text fallback:** now hedged across two text models (Marathi fell back to rules in the live check).
- **Live verifier:** healthy and defect uploads on every line, plus an opt-in rate-limit check.

## 2. Before / After Comparison

| Probe | Baseline (Pre-Fix, §2.3) | After Fixes (Measured Local / Verified Code) |
| --- | --- | --- |
| Path traversal (`..%2f..%2fetc%2fos-release`) | Arbitrary file read | Blocked (`404` / never leaks files; `tests/test_security.py`) |
| API key storage | Plain `--set-env-vars` | Secret Manager `--set-secrets=GEMINI_API_KEY=gemini-api-key:latest` |
| Tier-1 verdict logic | Scenario name (`LINE_D_HEALTHY` hard-coded) | Deterministic DSP + hedged visual gate (`gemini-3.5-flash-lite` → `gemma-4-26b-a4b-it` → `gemini-3.1-flash-lite`), fail-safe |
| Mock images | Text naming defect + scenario key + `SynthID` footer | Zero text (`eval/mock_rig_contact_sheet.png`), hidden `manifest.json` |
| Tier-2 primary model | Mislabelled `gemini-4-hydrogen (Live via 3.1-flash-lite)` | Benchmark-selected `gemini-3.1-flash-lite` hedged with `gemini-3.5-flash-lite` |
| Upload of a defect image | Passed (spall image under `LINE_D_HEALTHY` → HEALTHY) | 7/7 upload cases correct in a real-API spot check (PCB, WELD by image; CNC by vibration telemetry) |
| Tier-3 visual card | Fixed `bbox_by_scenario` labelled `Nano Banana SynthID` | Deterministic overlay of model `bbox` only (no box on `NO_DEFECT_FOUND`) |
| SOP retrieval | Hash bag-of-words + forced `max(sim, 0.96)` | `gemini-embedding-2` (`768-D`) over 18 SOPs + labelled keyword fallback |
| Economics | LLM prompt `integer > 25000` | Deterministic `economics.py` (`docs/ASSUMPTIONS.md`), `₹0` nominal |
| Human approval | None | Mandatory QE/Supervisor disposition before work order |
| Offline test suite | 7/7 in `180 s` (live API, scripted assertions) | 32 passed + 1 live test skipped, ~3 s (offline, zero scripted verdict assertions) |

## 3. Eval Headline Numbers (from `eval/RESULTS.md`)

> Measured on simulated inputs generated by backend/mock_rig (organiser-approved, no hardware). Not field accuracy.

30 parts (10 per line), real free-tier Gemini calls, in-process run after the post-audit fixes:

| Measure | Before fixes (18 parts) | After fixes (30 parts) |
| --- | --- | --- |
| True defects escalated | 7/7 | 10/10 |
| Healthy + hard negatives cleared | 0/11 (every part escalated; visual gate unavailable 15/18) | 20/20 |
| Visual gate answered by a model | 3/18 | 29/30 (hedge across 3 models) |
| Tier-2 defect type, Gemini answers | 4/4 (+2 rule answers counted together as "6/7") | 6/8 (+2/2 rule answers, reported separately) |
| Token effect of the gate | reported as "41.8% saving" (artifact of failed calls) | +22.3% (76,269 vs 98,190), method fixed |
| End-to-end p50 / p95 | 16.2 / 20.7 s | 8.1 / 22.0 s |

Caveats: retrieval used the keyword fallback in this run (SDK bug, fixed afterwards); the run used `google-genai` 2.8 on the laptop while the container pins 1.20; a live-URL eval (`--target live`) has not been run on the fixed build yet.

## 4. Model Routing Decisions & Benchmarks

> Measured on simulated inputs generated by backend/mock_rig (organiser-approved, no hardware). Not field accuracy.

**T1-B visual gate** (`eval/visual_gate_benchmark.md`; 46 frames in upload mode; rule fixed before the run: highest visible-defect recall with answer rate ≥ 75% and false-alarm rate ≤ 30%)

| Model | Answered | Visible defects caught | False alarms | p50 ms | Role |
| --- | ---: | ---: | ---: | ---: | --- |
| `gemini-3.5-flash-lite` | 46/46 | 14/14 | 0/32 | 2,476 | Primary |
| `gemma-4-26b-a4b-it` | 34/46 | 12/12 | 0/22 | 5,093 | First hedged backup; on-prem edge-client model |
| `gemini-3.1-flash-lite` | 46/46 | 12/14 | 1/32 | 6,150 | Second hedged backup |

**T2 diagnosis** (`eval/model_selection.md`, run 2; 8 escalated defect samples; highest agreement with p95 ≤ 10 s)

| Model | Success | Agreement | p50 ms | p95 ms | Role |
| --- | ---: | ---: | ---: | ---: | --- |
| `gemini-3.1-flash-lite` | 8/8 | 6/8 | 4,519 | 6,158 | Primary |
| `gemini-3.5-flash-lite` | 8/8 | 6/8 | 6,379 | 9,892 | Hedged runner-up (starts at 5.7 s) |
| `gemini-3.6-flash` | 2/8 | 1/8 | 14,844 | 15,477 | Not used (timeouts) |
| `gemini-3.8-flash` | 0/8 | 0/8 | — | — | Not used (`429` quota on every call) |

Run 1 (`eval/model_selection_run1.md`) also tried `gemini-4-hydrogen` (0/8, 503s/timeouts) and `gemini-3.5-flash` (0/8).

## 5. User Actions Still Required
1. **Rotate `GEMINI_API_KEY`** in Google AI Studio (restrict to Generative Language API) and upload it to Secret Manager (`gemini-api-key:latest`).
2. **Approve redeploying Cloud Run** with the post-audit fixes, then run `scripts/verify_live.py` against it.
3. **Billing decision:** You chose to stay on the free tier. Expect `503`/`429` spikes during judging; the hedges and fail-safe hold reduce but do not remove them.
4. **Record 3:00 demo video** following `docs/DEMO_SCRIPT.md` against the deployed Cloud Run URL.
5. **Customer evidence:** Fill `docs/CUSTOMER_EVIDENCE.md` if any plant interviews are conducted before submission (otherwise keep the honest "not yet done" statement).
6. **Merge & push approval:** Approve merging `improve/jury-fixes` into `main` and pushing after Phase 10 live verification.

## 6. Open Risks for Judging Day
- **Free-tier `503`/`429`:** the main risk. Hedging across three visual-gate models and two Tier-2 models reduces it; when all fail, parts are held for human review (fail-safe), so a healthy part can show HOLD during an outage. `gemini-3.8-flash` and all Nano Banana image models have no quota on this key.
- **Synthetic data is easy:** perfect gate scores on clean procedural frames will not carry over to real photos; no real-image accuracy is measured. Judges uploading their own photos may see misses or false alarms.
- **Retrieval ranking:** real embeddings put the right SOP in the top 3 but often not first; Tier-2 picks the final SOP. The UI shows the ranked list, so a judge may see a related-but-wrong SOP at the top.
- **Cloud Run cold starts & SQLite reset:** `--min-instances=1` reduces cold starts; container recycles reset demo data (labelled in the UI).
- **Rate limit (`30 req / 10 min` per IP):** a shared venue NAT could hit HTTP 429.
- **Browser speech support:** `SpeechRecognition` needs Chrome/Edge; others type instead.

## 7. Harsh Self-Score Against Jury Rubric

| Criterion (Weight) | Score | Evidence |
| --- | ---: | --- |
| Functional product (30%) | **22 / 30** | Blind rig, DSP gate, hedged visual gate (30/30 gate decisions locally, 7/7 upload spot checks), disposition-gated work orders, co-pilot. Deducted: fixes not yet redeployed or verified live, free-tier outages still cause holds, no recorded demo video. |
| Technical architecture (20%) | **17 / 20** | Deterministic DSP + fail-safe gate, staggered hedges with full attempt provenance, SOP numeric guard, deterministic economics, benchmark-driven routing, 32 offline tests. Deducted: SQLite demo store, laptop SDK differs from container pin. |
| Google AI integration depth (20%) | **15 / 20** | Five models in non-overlapping, measured roles (`gemini-3.5-flash-lite`, `gemma-4-26b-a4b-it`, `gemini-3.1-flash-lite`, `gemini-embedding-2`, `gemini-3.8-live`). Deducted: no image generation (quota), retrieval ranking weak, eval retrieval ran on fallback. |
| Problem–solution fit (15%) | **8 / 15** | Sound domain physics and human-in-the-loop design. Deducted: no customer interviews, unvalidated economics, synthetic-only accuracy. |
| UX / accessibility (10%) | **8 / 10** | Operator/Engineer views, EN/हिन्दी/मराठी, ≥12 px text, aria labels, "Not estimated" on rule holds. Not re-checked in a browser after this pass. |
| Innovation (5%) | **3 / 5** | Closed loop from detection to vernacular SOP guidance to human disposition to work order, with honest token accounting. |
| **Total** | **73 / 100** | A jury would also mark down the missing slide deck and demo video, which are outside this rubric table. |
