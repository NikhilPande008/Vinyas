# Vinyas — Pune City Buildathon Readiness & Hardware Integration Tracker (`TODO.md`)

**Team Vinyas:** Nikhil Pande & Ravi Mule (Startup Buildathon India 2026)  
**Architecture Baseline:** 4-Tier Edge-to-Cloud Architecture (`LIVE_HARDWARE` & `DEMO_SAFE_MODE`) — Stereo 48 kHz USB ADC, Primary Vibration + Coherence Booster DSP, Deterministic Physics Control-Plan Solver, ECDSA P-256 / Cloud KMS Signed Pillow Certificates, and Fragment-Isolated Streamlit UI.

---

## Completed V2.1 Foundation (Phases 1–5)
- [x] Initial 4-tier repository scaffold, Pydantic schemas, 14 reference JPEGs, synthetic 48 kHz WAV stems, Stage A/B edge modules, 4-agent pipeline, FastAPI server, and Streamlit `@st.fragment` UI.

---

## Phase 6: Pune City Buildathon Upgrade & Live Hardware Integration

- [x] **Task 6.1: Configuration, Control Plan Limits, Drawing Spec Rubric & Upgraded Schemas**
  - **Files:** `requirements.txt`, `.env.example`, `config/settings.py`, `config/control_plan_limits.json`, `config/drawing_spec_rubric.md`, `backend/models/schemas.py`, `data/fallback_cache/*.json`
  - **Scope:**
    - Add `HARDWARE_SOURCE`, `AUDIO_DEVICE_INDEX`, `CAMERA_DEVICE_INDEX`, `RELAY_SERIAL_PORT`, `VIBRATION_G_PER_FS`, and updated model IDs (`gemini-2.5-flash`, `gemma-3n-E4B-it` / `gemma-3-4b-it`, `gemini-3-pro-image-preview`).
    - Create `config/control_plan_limits.json` (`[70, 110]` feedrate dial %, `[80, 115]` spindle speed dial %, `[0.65, 1.15]` relative chip-load ratio) and `config/drawing_spec_rubric.md` (14-Reference taxonomy `REF-01`..`REF-14`, >1,250 tokens).
    - Add `InCycleTelemetrySummary` (with `cycle_id`), `DiagnosticEvidence`, `DeterministicControlSolution`, `RemediationPlan` (`served_from_fallback: bool = False`), and update `AOIInspectionResult` & `SanitizedVoiceIntent`.
  - **Verification:** `pytest -v`

- [x] **Task 6.2: Tier 2 Edge Upgrade — Live USB Stereo ADC, Primary Vibration + Coherence Booster DSP (`resample_poly`) & Dual-Mode Serial Hardware Relay**
  - **Files:** `edge/hilbert_envelope_dsp.py`, `edge/hardware_relay.py`, `edge/sensor_daemon.py`, `tests/test_hilbert_dsp_latency.py`
  - **Scope:**
    - Upgrade `edge/hilbert_envelope_dsp.py`: Ch 0 `2000–8000 Hz` band power ratio & spectral crest factor as primary chatter detector (protects light finishing cuts), Hilbert Envelope Coherence (`scipy.signal.coherence` after `250 Hz` LPF + `[::24]` decimation) as confidence booster, wrench-strike rejection for brief impulses with flat Ch 1 load, and `scipy.signal.resample_poly(stereo_chunk, up=1, down=3, axis=0)` for anti-aliased 16 kHz downsampling.
    - Upgrade `edge/hardware_relay.py`: Implement `HardwareRelayController` with `pyserial` USB relay support + mock driver and switchable `DAY1_ANDON_ONLY` vs. `DAY30_EXT_FEED_HOLD_CUTOUT` modes.
    - Upgrade `edge/sensor_daemon.py`: Real-time `(12000, 2)` 48 kHz capture via `sounddevice` (with `pyaudio` fallback) when `HARDWARE_SOURCE == "USB_STEREO_ADC"` and automatic fallback to WAV replay if unplugged.
  - **Verification:** `pytest tests/test_hilbert_dsp_latency.py -v`

- [x] **Task 6.3: Tier 3 Deterministic Physics Solver, Payback ROI Calculator, KMS Signed Pillow Certificates & Fallback-Aware Circuit Breaker**
  - **Files:** `backend/skills/control_plan_solver.py`, `backend/skills/roi_calculator.py`, `backend/services/kms_certificate_service.py`, `backend/services/circuit_breaker.py`, `backend/services/nanobanana_aoi_service.py`, `backend/services/gemini_omni_service.py`, `backend/agents/planner_agent.py`, `backend/agents/validator_agent.py`, `backend/agents/orchestrator.py`, `backend/main.py`, `tests/test_ppap_sandbox.py`, `tests/test_circuit_breaker_types.py`
  - **Scope:**
    - Create `backend/skills/control_plan_solver.py` ("Physics Calculates, AI Diagnoses"): computes & clamps `operator_feedrate_dial_pct`, `spindle_speed_dial_pct`, and `relative_chip_load_ratio` within `[0.65, 1.15]` with `[PASS]` badges.
    - Upgrade `backend/skills/roi_calculator.py` with validated `1.6-month (~48 days)` net hardware payback calculation.
    - Create `backend/services/kms_certificate_service.py` rendering high-contrast Pillow QA / Foundry Chargeback Certificates binding `cycle_id` + raw frame SHA-256 and signing with Cloud KMS `EC_SIGN_P256_SHA256` (local `cryptography` ECDSA P-256 offline fallback).
    - Upgrade `backend/services/circuit_breaker.py` to set `result.served_from_fallback = True` on fallback responses.
    - Wire new services, `cycle_id` correlation, and relay mode toggle into `backend/main.py` and agents.
  - **Verification:** `pytest tests/test_ppap_sandbox.py tests/test_circuit_breaker_types.py -v`

- [x] **Task 6.4: Tier 4 UI Upgrade — Honest Header Telemetry Badge, Fault Injection Studio & Signed Certificate Views**
  - **Files:** `frontend/app.py`, `frontend/components/supervisor_cockpit.py`, `frontend/components/operator_ptt_view.py`, `frontend/components/qa_inspector_view.py`, `frontend/components/fault_injection_studio_view.py`
  - **Scope:**
    - Update header badge to `[Alert Latency: <300ms | Source: LIVE_USB / SIMULATED | Fallback: FALSE/TRUE]` and add relay mode toggle (`DAY1_ANDON_ONLY` / `DAY30_EXT_FEED_HOLD_CUTOUT`).
    - Create `frontend/components/fault_injection_studio_view.py` (stereo fault injection + Nano Banana Pro Day-0 synthetic defect preview).
    - Surface deterministic physics solver outputs, `1.6-month (~48 days)` payback metric, `cycle_id` correlation, and downloadable ECDSA-signed Pillow QA Certificate PNG in the cockpit and QA inspector views.
  - **Verification:** `python3 -c "import frontend.app, frontend.components.fault_injection_studio_view, frontend.components.supervisor_cockpit, frontend.components.qa_inspector_view, frontend.components.operator_ptt_view; print('Task 6.4 OK')"`

- [x] **Task 6.5: Live Hardware Calibration & Diagnostics CLI (`scripts/verify_hardware_rig.py`) & Full E2E Verification**
  - **Files:** `scripts/verify_hardware_rig.py`, `tests/test_stage_rehearsal_e2e.py`
  - **Scope:**
    - Check 1: Stereo 48 kHz Audio Interface Discovery (`sounddevice`), 3-second RMS & peak frequency calibration on Ch 0 & Ch 1 for `VIBRATION_G_PER_FS` and `CT_AMPS_PER_FS`.
    - Check 2: Live Wrench-Strike vs. Chatter Loopback Test executing `stage_a_deterministic_fast_path()`, printing CPU time (`<2.0 ms`), vibration crest factor, envelope coherence, and state.
    - Check 3: USB Camera & V-Block Capture Test (`CAMERA_DEVICE_INDEX`), crops/resizes to `512x512` JPEG (`<60 KB`), computes SHA-256 digest, and generates signed Pillow QA Certificate at `data/test_certificate.png`.
    - Check 4: USB Relay / Andon Toggle Test cycling `GREEN_NOMINAL` -> `YELLOW_M01_HOLD` -> `RED_PREEMPT` and verifying `DAY30_EXT_FEED_HOLD_CUTOUT`.
  - **Verification:** `python3 scripts/verify_hardware_rig.py --simulate` and `pytest -v`
