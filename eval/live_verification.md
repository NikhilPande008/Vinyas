# Live Deployment Verification (`eval/live_verification.md`)

- **Target URL:** https://vinyas-ai-65216244490.asia-south1.run.app
- **Timestamp (UTC):** 2026-11-20T16:57:40.532818+00:00

## 1. Security — Path Traversal
- `GET /..%2f..%2frequirements.txt` → HTTP `404` | Blocked: `True`

## 2. Health & Metrics
- `storage_mode`: `DEMO_SQLITE` (`Demo SQLite store — resets when the server restarts`)
- `retrieval_mode`: `EMBEDDING_COSINE (gemini-embedding-2)`
- `routing_config`: `{"t1a_signal_gate": "deterministic DSP (NumPy/SciPy)", "t1b_visual_gate_primary": "gemma-4-26b-a4b-it", "t1b_visual_gate_fallback": "gemini-3.1-flash-lite", "t2_diagnosis_primary": "gemini-3.1-flash-lite", "t2_diagnosis_fallback": "gemini-3.8-flash", "t2_hedge_delay_sec": 6.0, "t3_visual_overlay": "deterministic Pillow overlay from T2 model bbox", "t4_copilot_primary": "gemini-3.8-live", "t4_copilot_fallback": "gemini-3.1-flash-lite", "retrieval_embedding": "gemini-embedding-2", "wo_extraction": "gemini-3.1-flash-lite"}`
- `/api/metrics` keys: `['routing_config', 'models']`

## 3. Blind Draws & Provenance
- `PCB-0002` (`PCB`): gate=`ESCALATE`, gt=`FLUX_RESIDUE_GLARE`, t1_model=`None`, t2_model=`gemini-3.1-flash-lite`, wall=`19485 ms`
- `PCB-0008` (`PCB`): gate=`ESCALATE`, gt=`INSUFFICIENT_SOLDER`, t1_model=`None`, t2_model=`None`, wall=`20454 ms`
- `PCB-0012` (`PCB`): gate=`HEALTHY`, gt=`NOMINAL`, t1_model=`gemini-3.1-flash-lite`, t2_model=`None`, wall=`6421 ms`
- `CNC-0013` (`CNC`): gate=`HEALTHY`, gt=`NOMINAL`, t1_model=`gemini-3.1-flash-lite`, t2_model=`None`, wall=`5478 ms`
- `CNC-0002` (`CNC`): gate=`ESCALATE`, gt=`OUTER_RACE_FAULT`, t1_model=`None`, t2_model=`None`, wall=`11758 ms`
- `CNC-0010` (`CNC`): gate=`HEALTHY`, gt=`NOMINAL`, t1_model=`gemini-3.1-flash-lite`, t2_model=`None`, wall=`9534 ms`
- `WELD-0008` (`WELD`): gate=`ESCALATE`, gt=`NOMINAL`, t1_model=`None`, t2_model=`gemini-3.1-flash-lite`, wall=`13363 ms`
- `WELD-0013` (`WELD`): gate=`ESCALATE`, gt=`SPATTER_COSMETIC`, t1_model=`None`, t2_model=`None`, wall=`12392 ms`
- `WELD-0002` (`WELD`): gate=`ESCALATE`, gt=`POROSITY_GAS_LOSS`, t1_model=`None`, t2_model=`None`, wall=`20060 ms`
- **Observed verdicts:** `['ESCALATE', 'HEALTHY']` | p50=`12392 ms` | p95=`20454 ms`

## 4. Custom Upload Test (PCB)
- Healthy upload (`PCB-0003`): gate=`ESCALATE`, input_simulated=`False`
- Defect upload (`PCB-0005`): gate=`HEALTHY`, input_simulated=`False`

## 5. Co-Pilot Multilingual Check
- `en-IN`: model=`gemini-3.8-live`, audio=`True`, latency=`10017 ms`
- `hi-IN`: model=`gemini-3.8-live`, audio=`True`, latency=`7435 ms`
- `mr-IN`: model=`FALLBACK_RULES`, audio=`False`, latency=`23059 ms`

## 6. Disposition & Work Order Gating
- Before disposition: HTTP `400` (expected 400)
- Record HOLD disposition: HTTP `200`
- After disposition: HTTP `200` (producer=`MODEL`)
