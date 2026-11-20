# Vinyas Claim Audit (`eval/claim_audit.md`)

Every numerical claim, model ID, standard, and architectural claim across `README.md`, `docs/*.md`, and `frontend/src/App.jsx` traced to its evidence.

| Claim | Location | Evidence | Status |
| --- | --- | --- | --- |
| Live Cloud Run deployment (`vinyas-ai`, `asia-south1`, port 8080) | `README.md`, `scripts/deploy_cloud_run.sh` | Cloud Run service config & deploy script | PROVEN |
| 60 seeded simulated samples (20/line), zero text on frames, hidden `manifest.json` | `README.md`, `docs/MOCK_RIG.md` | `backend/mock_rig/dataset.py`, `eval/mock_rig_contact_sheet.png`, `tests/test_mock_rig.py` | PROVEN |
| Representative 7014C bearing geometry (`n=20, d=11.1 mm, D=90 mm, α=15°`, `5400 rpm` → `BPFO ≈ 793 Hz`) | `docs/ASSUMPTIONS.md`, `docs/MOCK_RIG.md`, `docs/JURY_QA.md` | `backend/mock_rig/vibration.py:compute_bearing_frequencies`, `tests/test_mock_rig.py` | ASSUMED-LABELLED |
| ISO 20816-3:2022 Group 2 rigid-support reference zones (`1.4 / 2.8 / 4.5 mm/s`) | `docs/ASSUMPTIONS.md`, `backend/dsp/envelope.py` | Verified via web search (replaces ISO 10816-3:2009); labelled reference scale only | PROVEN |
| SAC305 reflow window (`1.0–3.0 °C/s`, `235–250 °C`, `45–90 s` TAL) & IPC-A-610 Class 3 | `docs/ASSUMPTIONS.md`, `backend/dsp/envelope.py` | Verified via web search | PROVEN |
| MIG shielding gas (`15–20 L/min`, 82/18 Ar/CO2) & AWS D8.8-style visual porosity criteria | `docs/ASSUMPTIONS.md`, `backend/dsp/envelope.py` | Verified via web search; labelled demo criteria (production follows OEM WPS) | PROVEN |
| T1-B visual gate hedges `gemini-3.5-flash-lite` → `gemma-4-26b-a4b-it` → `gemini-3.1-flash-lite` | `README.md`, `/health`, `/api/metrics` | `eval/visual_gate_benchmark.md` (46 frames, rule fixed before the run), `backend/config.py:t1b_candidates`, `tests/test_jury_fixes.py` | PROVEN |
| T2 primary `gemini-3.1-flash-lite`, hedged with `gemini-3.5-flash-lite` (`gemini-4-hydrogen` 0/8 in run 1; `gemini-3.8-flash` no quota in run 2) | `README.md`, `docs/DECK_OUTLINE.md`, `/health` | `eval/model_selection.md`, `eval/model_selection_run1.md` | PROVEN |
| Retrieval uses `gemini-embedding-2` (`768-D`) over 18 SOPs, keyword fallback labelled | `README.md`, `backend/db/demo_store.py` | Live `embed_content` verification + `tests/test_phase5.py` | PROVEN |
| T3 is deterministic Pillow overlay of model bbox (Nano Banana omitted due to 429 quota) | `README.md`, `frontend/src/App.jsx`, `backend/services/overlay.py` | Live 429 verification on all 4 Nano Banana models + `tests/test_phase4.py` | PROVEN |
| T4 uses `gemini-3.8-live` over `WS /api/live-copilot` (15 s timeout, audio + transcript) | `README.md`, `frontend/src/App.jsx`, `backend/main.py` | Live `gemini-3.8-live` verification (112 KB PCM audio) + `tests/test_phase4.py` | PROVEN |
| Storage is SQLite demo store (resets on restart); AlloyDB schema in `infra/alloydb_schema.sql` not deployed | `README.md`, `frontend/src/App.jsx`, `/health` | `backend/db/demo_store.py`, `infra/alloydb_schema.sql`, `tests/test_phase5.py` | PROVEN |
| INR avoidable-loss constants (`₹2,850` / `₹6,400` / `₹9,200`, hourly downtime, mins by severity) | `docs/ASSUMPTIONS.md`, `backend/services/economics.py` | Explicitly labelled "team assumption, unvalidated"; `₹0` on nominal parts | ASSUMED-LABELLED |
| Customer validation status | `README.md`, `docs/CUSTOMER_EVIDENCE.md` | Explicitly states "not yet done"; zero fabricated quotes/OEMs | PROVEN |
| Competitor descriptions & URLs (Infinite Uptime, Altizon, Tractian, Augury, Nanoprecise, LandingLens, Google Visual Inspection AI, Siemens Senseye) | `README.md` | Verified via web search | PROVEN |
| Gate confusion matrix, recall, latencies, token accounting | `README.md`, `eval/RESULTS.md` | Produced by `scripts/eval_pipeline.py` with verbatim simulated-input header | PROVEN |
| Token effect of the gate (escalations charged at mean measured T2 cost; negative when most parts escalate) | `README.md`, `docs/ASSUMPTIONS.md`, line-run UI | `backend/services/metrics.py:compute_gate_token_accounting`, `tests/test_jury_fixes.py` | PROVEN |
| Earlier "41.8% measured token saving" | old `README.md` | Was an artifact of 10 failed Tier-2 calls costing 0 tokens while all 18 parts escalated | REMOVED |
| Earlier "Tier-2 agreement 6/7" without source split | old `README.md` | 2 of the 6 came from rule-based fallback; the report now splits model vs rules | REMOVED (replaced by split) |
| DSP gate thresholds (BPFO SNR ≥ 14 dB, 2× ≥ 11 dB) and calibration (19/21 defects, 0/39 false flags) | `docs/MOCK_RIG.md`, `SKILL.md` | `scripts/calibrate_dsp_gate.py` → `eval/dsp_gate_calibration.md`; `tests/test_jury_fixes.py` checks SKILL.md matches code | PROVEN |
| Visual gate catches visible defects on uploads | `docs/JURY_QA.md`, `README.md` | `eval/visual_gate_benchmark.md` (synthetic frames; bridges redrawn as solder before the run, logged in `docs/MOCK_RIG.md`) | PROVEN (simulated) |
| Legacy claims (`SynthID`, `95.4%`, `<50 ms`, `3x faster`, `sub-10ms`, `AlloyDB Express` runtime, `4.21 kHz BPFO`, `Tata Motors`, fake latency defaults) | All files | Verified absent via `tests/test_ui_hygiene.py` | REMOVED |
