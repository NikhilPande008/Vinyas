# Jury Q&A — One-Breath Answers (`docs/JURY_QA.md`)

1. **Which model produced this output?**
   Every stage returns a `StageProvenance` object naming the exact `model_id` (or `DETERMINISTIC` / `FALLBACK_RULES`), status, latency, and token counts; in Engineer view, the "Attempts trace" disclosure shows every model tried in order.
2. **Upload a healthy part / a defect: what happens?**
   Custom uploads bypass `mock_rig` and run through deterministic T1-A checks (using the user's selected telemetry preset, nominal by default). On PCB and WELD, the T1-B visual gate (hedged: `gemini-3.5-flash-lite`, then `gemma-4-26b-a4b-it`, then `gemini-3.1-flash-lite`) screens the uploaded image and escalates only if a gate flags an anomaly or every visual model is unavailable; no scenario name overrides the verdict. On CNC, T1-B is marked `SKIPPED` (`bearing not visible; vibration-led`) so the DSP vibration gate decides directly (the UI offers nominal/anomalous telemetry presets). Measured: `eval/visual_gate_benchmark.md`.
3. **Show the BPFO maths.**
   In `backend/mock_rig/vibration.py` and `backend/dsp/envelope.py`, `BPFO = (n/2)·f_r·(1 − (d/D)·cos α)`. For a representative 7014C-class bearing (`n=20, d=11.1 mm, D=90 mm, α=15°`) at `5,400 rpm` (`f_r=90 Hz`), `BPFO ≈ 793 Hz`. Impacts excite a `~4.2 kHz` structural resonance, which we demodulate via `2–8 kHz` Butterworth bandpass → `|hilbert|` envelope → FFT.
4. **Why vision isn't used for bearings, and who owns the quality decision?**
   A rolling-element bearing sits inside the assembled spindle housing, so a camera cannot see raceway spalling — CNC detection is vibration-led. On every line, the AI only recommends; a human QE or Supervisor must record `RELEASE / HOLD / REWORK / SCRAP` before a work order can be logged, and nothing actuates a machine.
5. **Why an LLM at Tier-1 at all?**
   Deterministic DSP (`T1-A`) handles periodic impacts and process windows in milliseconds at zero token cost — and on CNC, T1-B is skipped completely (`bearing not visible; vibration-led`) so healthy spindles never pay vision tokens or latency. On PCB and WELD, a cheap visual gate (`T1-B`: `gemini-3.5-flash-lite`, hedged with `gemma-4-26b-a4b-it` and `gemini-3.1-flash-lite`) screens optical defects (bridges, starved joints, porosity) before the heavier Tier-2 SOP reasoning. The token effect is measured in `eval/RESULTS.md`; it is only a saving when the gate clears most healthy parts.
6. **Where's AlloyDB?**
   Not deployed in this demo. The hosted service honestly uses a SQLite demo store (which resets on container restart) plus real `gemini-embedding-2` cosine similarity over 18 SOPs; the production PostgreSQL + `pgvector(768)` schema lives in `infra/alloydb_schema.sql`.
7. **Who will pay?**
   Customer validation is not yet done (documented honestly in `docs/CUSTOMER_EVIDENCE.md`); our planned pilot target is Pune Tier-2/3 automotive component suppliers in Chakan/Bhosari, and all INR loss estimates in `docs/ASSUMPTIONS.md` are explicitly labelled as unvalidated team assumptions.
8. **Why you vs Infinite Uptime, Tractian, Google Visual Inspection AI?**
   Those incumbents excel at either dedicated vibration sensors (Infinite Uptime, Tractian, Augury) or cloud vision models (Visual Inspection AI, LandingLens). Vinyas focuses on closing the shop-floor loop in one workflow: multi-modal gating (DSP + vision) → SOP-guarded repair steps in EN/Hindi/Marathi → mandatory human disposition → multilingual work-order extraction.
9. **What breaks at 10× load?**
   In-memory per-IP rate limiting (30 req/10 min) and free-tier Gemini API quota (`503 UNAVAILABLE` spikes observed during our benchmark, plus `429` on Nano Banana image models) are the first bottlenecks; Cloud Run scales up to `--max-instances=4 --concurrency=20`, and production would require paid Vertex AI provisioned throughput plus managed Cloud SQL/AlloyDB.
10. **What did you deliberately not build?**
    No PLC/machine actuation, no unverified AlloyDB runtime claims, no Nano Banana runtime image generation (all 4 image models returned 429 quota on this key), no fake hardware rig claims, and no invented customer testimonials.
