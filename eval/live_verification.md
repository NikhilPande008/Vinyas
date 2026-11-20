# Live Deployment Verification (`eval/live_verification.md`)

- **Target URL:** https://vinyas-ai-65216244490.asia-south1.run.app
- **Timestamp (UTC):** 2026-11-20T18:06:47.658178+00:00

## 1. Security — Path Traversal
- `GET /..%2f..%2frequirements.txt` → HTTP `404` | Blocked: `True`

## 2. Health & Metrics
- `storage_mode`: `DEMO_SQLITE` (`Demo SQLite store — resets when the server restarts`)
- `retrieval_mode`: `EMBEDDING_COSINE (gemini-embedding-2)`
- `routing_config`: `{"t1a_signal_gate": "deterministic DSP (NumPy/SciPy)", "t1b_visual_gate_primary": "gemini-3.5-flash-lite", "t1b_visual_gate_fallback": "gemma-4-26b-a4b-it", "t1b_hedge_order": ["gemini-3.5-flash-lite", "gemma-4-26b-a4b-it", "gemini-3.1-flash-lite"], "t1b_hedge_delay_sec": 3.0, "t2_diagnosis_primary": "gemini-3.1-flash-lite", "t2_diagnosis_fallback": "gemini-3.5-flash-lite", "t2_hedge_delay_sec": 5.7, "t3_visual_overlay": "deterministic Pillow overlay from T2 model bbox", "t4_copilot_primary": "gemini-3.8-live", "t4_copilot_fallback": "gemini-3.1-flash-lite", "retrieval_embedding": "gemini-embedding-2", "wo_extraction": "gemini-3.1-flash-lite"}`
- `/api/metrics` keys: `['routing_config', 'models']`

## 3. Blind Draws & Provenance
- `PCB-0005` (`PCB`): gate=`ESCALATE`, gt=`SOLDER_BRIDGE`, t1_model=`gemini-3.1-flash-lite`, t2_model=`gemini-3.1-flash-lite`, wall=`12637 ms`
- `PCB-0009` (`PCB`): gate=`HEALTHY`, gt=`NOMINAL`, t1_model=`gemini-3.1-flash-lite`, t2_model=`None`, wall=`7027 ms`
- `PCB-0005` (`PCB`): gate=`ESCALATE`, gt=`SOLDER_BRIDGE`, t1_model=`gemma-4-26b-a4b-it`, t2_model=`gemini-3.1-flash-lite`, wall=`9711 ms`
- `CNC-0004` (`CNC`): gate=`HEALTHY`, gt=`NOMINAL`, t1_model=`gemini-3.1-flash-lite`, t2_model=`None`, wall=`5991 ms`
- `CNC-0012` (`CNC`): gate=`HEALTHY`, gt=`NOMINAL`, t1_model=`gemini-3.1-flash-lite`, t2_model=`None`, wall=`5451 ms`
- `CNC-0003` (`CNC`): gate=`HEALTHY`, gt=`WRENCH_STRIKE`, t1_model=`gemini-3.1-flash-lite`, t2_model=`None`, wall=`7270 ms`
- `WELD-0015` (`WELD`): gate=`HEALTHY`, gt=`NOMINAL`, t1_model=`gemini-3.1-flash-lite`, t2_model=`None`, wall=`8217 ms`
- `WELD-0005` (`WELD`): gate=`HEALTHY`, gt=`NOMINAL`, t1_model=`gemini-3.1-flash-lite`, t2_model=`None`, wall=`9733 ms`
- `WELD-0006` (`WELD`): gate=`HEALTHY`, gt=`NOMINAL`, t1_model=`gemini-3.1-flash-lite`, t2_model=`None`, wall=`6880 ms`
- **Observed verdicts:** `['ESCALATE', 'HEALTHY']` | p50=`7270 ms` | p95=`12637 ms`

## 4. Custom Upload Test (healthy vs defect, every line)
- PCB NOMINAL upload (`PCB-0003`): gate=`HEALTHY` (expected `HEALTHY`, OK), visual vote=`NOMINAL` by `gemini-3.1-flash-lite`, input_simulated=`False`
- PCB SOLDER_BRIDGE upload (`PCB-0005`): gate=`ESCALATE` (expected `ESCALATE`, OK), visual vote=`ANOMALY` by `gemini-3.1-flash-lite`, input_simulated=`False`
- WELD NOMINAL upload (`WELD-0001`): gate=`HEALTHY` (expected `HEALTHY`, OK), visual vote=`NOMINAL` by `gemini-3.1-flash-lite`, input_simulated=`False`
- WELD POROSITY_GAS_LOSS upload (`WELD-0002`): gate=`ESCALATE` (expected `ESCALATE`, OK), visual vote=`ANOMALY` by `gemini-3.1-flash-lite`, input_simulated=`False`
- CNC NOMINAL upload (`CNC-0004`): gate=`HEALTHY` (expected `HEALTHY`, OK), visual vote=`NOMINAL` by `gemini-3.1-flash-lite`, input_simulated=`False`
- CNC OUTER_RACE_FAULT upload (`CNC-0001`, Zone-C telemetry): gate=`ESCALATE` (expected `ESCALATE`, OK), visual vote=`NOMINAL` by `gemini-3.1-flash-lite`, input_simulated=`False`

## 5. Co-Pilot Multilingual Check
- `en-IN`: model=`gemini-3.8-live`, audio=`True`, latency=`7279 ms`
- `hi-IN`: model=`gemini-3.8-live`, audio=`True`, latency=`7233 ms`
- `mr-IN`: model=`gemini-3.8-live`, audio=`True`, latency=`6736 ms`

## 6. Disposition & Work Order Gating
- Before disposition: HTTP `400` (expected 400)
- Record HOLD disposition: HTTP `200`
- After disposition: HTTP `200` (producer=`MODEL`)
