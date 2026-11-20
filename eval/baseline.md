# Vinyas Baseline Measurements (Pre-Fix Audit)

**Recorded:** 2026-11-20 (before Phase 0 fixes)
**Target:** `https://vinyas-ai-65216244490.asia-south1.run.app` (initial deployment)

| Probe | Baseline Result |
| --- | --- |
| `/health` | `storage_mode: LOCAL_SQLITE_FALLBACK`, `db_ai_mode: PYTHON_FALLBACK`, `inference_mode: LIVE_GOOGLE_AI` (static claim) |
| Tier-1 latency (A / B / C / D) | `21,027 / 14,085 / 2,428 / 2,048 ms` (A & B fell back after two 10.5 s timeouts; README claimed `<50 ms`) |
| End-to-end wall time (A / B / C / D) | `24.9 s / 20.6 s / 7.0 s / 2.2 s` |
| Tier-2 model that actually answered | `gemini-3.1-flash-lite` every time, mislabelled `gemini-4-hydrogen (Live via gemini-3.1-flash-lite)` |
| `gemini-4-hydrogen` direct call | `503 UNAVAILABLE` after `7.0 s` |
| `gemini-nano-banana-2.1` direct call | `429 RESOURCE_EXHAUSTED` (no quota on project key) |
| Tier-3 output | Pillow fallback every time, displayed under a hard-coded `NANO BANANA 2.1 … SynthID` header |
| `gemini-3.8-live` direct call (local) | Works (`7.05 s` short reply); router timeout was `7.5 s`; Cloud Run fell back to `flash-lite` (`1.1 s`) |
| Spall image uploaded under `LINE_D_HEALTHY` | `HEALTHY` (defect passed through) |
| Healthy image uploaded under `LINE_A_PCB` | `ESCALATE`, then diagnosis `NOMINAL-BASELINE-PASS` with `₹45,000 saved` |
| Path traversal on SPA catch-all | Arbitrary file read confirmed in pre-fix audit (remediated in Phase 0) |
| `pytest` | 7/7 passed in `180 s` (hit live API; asserted hard-coded branches) |
