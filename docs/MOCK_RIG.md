# Vinyas Mock Rig v2 (`backend/mock_rig/`)

## Organiser Ruling
Per Startup Buildathon India 2026 organiser confirmation, physical factory hardware is **not required**; simulated sensor and camera inputs are permitted provided:
1. Inputs are physically plausible and contain **no answer leakage** (no defect names, scenario labels, or watermarks on images).
2. The DSP and AI models genuinely decide from the input signals and images.
3. Every simulated input is explicitly labelled `"SIMULATED INPUT"` in the API, UI, and documentation.

## Dataset Composition (`seed=2026`, 60 samples)
Each of the three production lines has **20 seeded samples** in shuffled order (`~50%` nominal, `~35%` true defects, `~15%` hard negatives):

| Line | Machine | Nominal (10) | True Defects (7) | Hard Negatives (3) |
| --- | --- | --- | --- | --- |
| **PCB** | SMT Reflow (`SMT-REFLOW-CHAKAN-A1`) | `NOMINAL` (10) | `SOLDER_BRIDGE` (4), `INSUFFICIENT_SOLDER` (3) | `FLUX_RESIDUE_GLARE` (3) |
| **CNC** | High-Speed Spindle (`CNC-SPINDLE-CHAKAN-B2`) | `NOMINAL` (10) | `OUTER_RACE_FAULT` (6: 4 severe, 2 mild), `IMBALANCE` (1) | `WRENCH_STRIKE` (3) |
| **WELD** | Robotic MIG Cell (`MIG-ARC-BHOSARI-C3`) | `NOMINAL` (10) | `POROSITY_GAS_LOSS` (7: 4 severe, 3 mild) | `SPATTER_COSMETIC` (3) |

Ground-truth labels live **exclusively** in `data/mock_rig/manifest.json`. The inference path (`backend/services/*` and `POST /api/inspect`) never opens `manifest.json`. Only the evaluation harness (`scripts/eval_pipeline.py`) and the post-inspection reveal endpoint (`GET /api/rig/reveal/{sample_id}`) read it.

## Physics & Synthesis Details

### CNC Spindle Vibration (`backend/mock_rig/vibration.py`)
- Sample rate: `48,000 Hz`, duration `1.0 s`, `float32` + 16-bit mono PCM WAV.
- Representative 7014C-class angular-contact bearing geometry (assumptions recorded in `docs/ASSUMPTIONS.md`): `n = 20` balls, `d = 11.1 mm`, `D = 90.0 mm`, contact angle `α = 15°`.
- Shaft speed: `5,400 rpm ± 35 rpm` (`f_r ≈ 90 Hz`).
- Bearing fault frequencies are computed from geometry and speed:
  - `BPFO = (n/2) · f_r · (1 - (d/D)·cos α) ≈ 793 Hz`
  - `BPFI = (n/2) · f_r · (1 + (d/D)·cos α) ≈ 1,007 Hz`
- `OUTER_RACE_FAULT`: impulse train at `BPFO` (`±1%` slip jitter), each impulse exciting a damped structural resonance (`f_res ≈ 4,050–4,350 Hz`, decay `~1 ms`).
- `WRENCH_STRIKE`: single non-periodic high-amplitude impact (`f_res ≈ 2,900–3,400 Hz`, decay `~3.2 ms`) producing high kurtosis without BPFO periodicity.
- `IMBALANCE`: elevated `1×` shaft harmonic (`~90 Hz`) pushing RMS velocity into ISO 20816-3 Zone C without BPFO periodicity.
- `vibration_rms_mms` is computed directly from the `10–1,000 Hz` Butterworth-bandpassed signal.

### Process Telemetry (`backend/mock_rig/process.py`)
- **PCB (SAC305 reflow):** nominal window `1.0–3.0 °C/s` preheat ramp, `235–250 °C` peak, `45–90 s` Time Above Liquidus (TAL). Roughly `30%` of defective PCB samples keep nominal reflow telemetry so optical inspection remains necessary.
- **MIG Weld (82% Ar / 18% CO2):** nominal shielding gas `15–20 L/min`, arc voltage `20–24 V`, wire feed `7.5–9.5 m/min`. `POROSITY_GAS_LOSS` drops gas flow to `5.2–10.8 L/min`; `SPATTER_COSMETIC` maintains nominal gas flow.

### Procedural Images (`backend/mock_rig/images.py`)
- Resolution: `768 × 512` PNG, with directional illumination gradient and Gaussian sensor noise. **Zero text** is rendered on any frame.
- **PCB:** 4-sided 64-lead QFP package with pads, copper traces, vias, and shape-only silkscreen. Bridges span 2–3 leads at a random side/pin; flux glare is a translucent patch off the leads.
- **WELD:** brushed steel plates with rippled weld bead; porosity clusters dark pits on the bead; cosmetic spatter places droplets beside the bead.
- **CNC:** machined metallic bore/flange surface with turning marks. Because the rolling bearing sits inside the assembled spindle housing, the camera frame shows no bearing defect; CNC detection is vibration-led.
