# Vinyas AI (V2.1) — Acoustic-Electrical & Polarized Optical Digital Twin

**Startup Buildathon India (Google DeepMind, Google Cloud, Hack2Skill, nasscom, HeadStart)**

Vinyas AI V2.1 is an edge-to-cloud industrial intelligence platform built for Indian Tier-1/Tier-2 discrete CNC manufacturing hubs (Pune-Chakan, Pimpri-Chinchwad, Chennai-Sriperumbudur, Coimbatore, Rajkot, Faridabad). It fuses **hardware-synchronized 48 kHz spindle acoustic emissions (AE)**, **non-invasive split-core motor current phase signatures**, and **air-purged polarized optical inspection** to catch CNC machining defects in-cycle—delivering **IATF 16949 PPAP-compliant** process stabilization and **Cloud KMS + SynthID** tamper-proof quality certificates without invasive Day-1 PLC wiring.

## Core V2.1 Architectural Highlights
1. **Stage A Deterministic DSP Fast-Path (`<1.4 ms`):** Processes a `(12000, 2)` 250 ms rolling stereo window at 48 kHz (`Ch0`: Contact Piezo AE, `Ch1`: Split-Core CT) using pre-compiled 4th-order Butterworth SOS filters, strips 20 ms startup transients, rejects floor/wrench shocks (`ct_ripple_std < 0.12 A`), and computes Hilbert Envelope Magnitude-Squared Coherence (`K=13` Welch segments, `30-250 Hz`).
2. **Stage B Sovereign Edge Triage (`~45 ms`):** Isolated `multiprocessing.Queue` worker running quantized `gemma-4-E2B-it-int4` / `gemma-3n-E4B-it-int4` (`keep_alive=-1`) to filter harmless roughing tool-entry transients locally.
3. **4-Agent Antigravity Control Plane:** Coordinates `DiagnosticExtractorAgent`, `PPAPPlannerAgent`, `SandboxSafetyValidatorAgent`, and `ShopFloorExecutorAgent` with deterministic `verify_ppap_window()` checks.
4. **>4,800-Token Pinned Context Cache & Dual Provenance:** Caches 14 visual reference tokens (`REF-01`..`REF-14`) + the IATF 16949 inspection rubric (`~4,862 tokens`) on `gemini-2.5-flash` and pairs deterministic **Cloud KMS / HMAC-SHA256** raw frame signatures with **Nano Banana Pro** (`gemini-2.5-flash-image`) **SynthID**-watermarked QA badges.
5. **Fragment-Isolated Streamlit >= 1.40 UI:** Isolates Supervisor Cockpit, Operator Marathi PTT View, 14-Ref QA Inspector, and Lyria Fault Studio with `@st.fragment` and a 1-click Live/Safe circuit breaker pill.

## Quickstart
```bash
pip install -r requirements.txt
pytest -v
uvicorn backend.main:app --reload --port 8000
streamlit run frontend/app.py
```
