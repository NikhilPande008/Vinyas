# Tier-2 Model Selection Benchmark (`eval/model_selection.md`)

Measured on **8 escalated simulated defect samples** from `backend/mock_rig` (3 PCB, 3 CNC, 2 WELD) using the full multimodal Tier-2 payload (frame PNG + CNC Hilbert envelope PNG + DSP features + SOPs + SKILL.md + strict Pydantic `response_schema`).

**Decision rule:** Highest defect-type agreement with `p95 <= 10,000 ms`; ties go to the faster (`p50`) model.

| Model ID | Success | Schema Valid | Defect Agreement | p50 (ms) | p75 (ms) | p95 (ms) | Mean In Tok | Mean Out Tok |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `gemini-4-hydrogen` | 0/8 | 0/8 | 0/8 | 9938 | 15223 | 15548 | 0 | 0 |
| `gemini-3.8-flash` | 0/8 | 0/8 | 0/8 | 5448 | 7166 | 14286 | 0 | 0 |
| `gemini-3.5-flash` | 0/8 | 0/8 | 0/8 | 14800 | 15009 | 15013 | 0 | 0 |
| `gemini-3.1-flash-lite` | 3/8 | 3/8 | 3/8 | 6367 | 10688 | 12721 | 2854 | 436 |
| `gemini-2.5-flash` | 0/8 | 0/8 | 0/8 | 612 | 622 | 963 | 0 | 0 |
| `gemini-2.5-flash-lite` | 0/8 | 0/8 | 0/8 | 584 | 693 | 868 | 0 | 0 |

## Routing Decision
- **Primary:** `gemini-3.1-flash-lite` (the only candidate with non-zero live availability during the benchmark: `3/8` total, `3/3` schema-valid and `3/3` defect-type agreement on successful responses; p50 `6367 ms`, p75 `10688 ms`, mean `2854` input / `436` output tokens).
- **Runner-up (hedged):** `gemini-3.8-flash` (configured as hedged fallback; `gemini-2.5-flash` and `gemini-2.5-flash-lite` returned `404 NOT_FOUND` on this key, and `gemini-4-hydrogen` / `gemini-3.5-flash` / `gemini-3.8-flash` experienced `503 UNAVAILABLE` high-demand errors during the benchmark window).
- **Hedge trigger delay:** `6.00 s` (capped at 6.0 s per Phase 4a rule).
- **Note:** `gemini-4-hydrogen` did **not** win and has been removed from headline claims; it appears only in this benchmark table.
