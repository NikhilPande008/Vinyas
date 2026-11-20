# Live Deployment Verification (`eval/live_verification.md`)

- **Target URL:** https://vinyas-ai-65216244490.asia-south1.run.app
- **Timestamp (UTC):** 2026-11-20T16:46:28.899126+00:00

## 1. Security — Path Traversal
- `GET /..%2f..%2frequirements.txt` → HTTP `404` | Blocked: `True`

## 2. Health & Metrics
- `storage_mode`: `DEMO_SQLITE` (`Demo SQLite store — resets when the server restarts`)
- `retrieval_mode`: `EMBEDDING_COSINE (gemini-embedding-2)`
- `routing_config`: `{"t1a_signal_gate": "deterministic DSP (NumPy/SciPy)", "t1b_visual_gate_primary": "gemma-4-26b-a4b-it", "t1b_visual_gate_fallback": "gemini-3.1-flash-lite", "t2_diagnosis_primary": "gemini-3.1-flash-lite", "t2_diagnosis_fallback": "gemini-3.8-flash", "t2_hedge_delay_sec": 6.0, "t3_visual_overlay": "deterministic Pillow overlay from T2 model bbox", "t4_copilot_primary": "gemini-3.8-live", "t4_copilot_fallback": "gemini-3.1-flash-lite", "retrieval_embedding": "gemini-embedding-2", "wo_extraction": "gemini-3.1-flash-lite"}`
- `/api/metrics` keys: `['routing_config', 'models']`

## 3. Blind Draws & Provenance
- `PCB-0015` (`PCB`): gate=`HEALTHY`, gt=`NOMINAL`, t1_model=`gemma-4-26b-a4b-it`, t2_model=`None`, wall=`4903 ms`
- `PCB-0006` (`PCB`): gate=`ESCALATE`, gt=`NOMINAL`, t1_model=`None`, t2_model=`None`, wall=`15457 ms`
- `PCB-0015` (`PCB`): gate=`HEALTHY`, gt=`NOMINAL`, t1_model=`gemini-3.1-flash-lite`, t2_model=`None`, wall=`5698 ms`
- `CNC-0018` (`CNC`): gate=`ESCALATE`, gt=`WRENCH_STRIKE`, t1_model=`None`, t2_model=`None`, wall=`21297 ms`
- `CNC-0012` (`CNC`): gate=`ESCALATE`, gt=`NOMINAL`, t1_model=`None`, t2_model=`None`, wall=`21025 ms`
- `CNC-0014` (`CNC`): gate=`ESCALATE`, gt=`NOMINAL`, t1_model=`None`, t2_model=`None`, wall=`13874 ms`
- `WELD-0017` (`WELD`): gate=`HEALTHY`, gt=`NOMINAL`, t1_model=`gemini-3.1-flash-lite`, t2_model=`None`, wall=`4940 ms`
- `WELD-0010` (`WELD`): gate=`ESCALATE`, gt=`NOMINAL`, t1_model=`None`, t2_model=`gemini-3.1-flash-lite`, wall=`12512 ms`
- `WELD-0006` (`WELD`): gate=`ESCALATE`, gt=`NOMINAL`, t1_model=`None`, t2_model=`None`, wall=`19514 ms`
- **Observed verdicts:** `['ESCALATE', 'HEALTHY']` | p50=`13874 ms` | p95=`21297 ms`

## 4. Custom Upload Test (PCB)
- Healthy upload (`PCB-0003`): gate=`ESCALATE`, input_simulated=`False`
- Defect upload (`PCB-0005`): gate=`HEALTHY`, input_simulated=`False`

## 5. Co-Pilot Multilingual Check
- `en-IN`: model=`gemini-3.8-live`, audio=`True`, latency=`10157 ms`
- `hi-IN`: model=`gemini-3.8-live`, audio=`True`, latency=`7772 ms`
- `mr-IN`: model=`FALLBACK_RULES`, audio=`False`, latency=`16939 ms`

## 6. Disposition & Work Order Gating
- Before disposition: HTTP `400` (expected 400)
- Record HOLD disposition: HTTP `200`
- After disposition: HTTP `200` (producer=`FALLBACK_RULES`)
