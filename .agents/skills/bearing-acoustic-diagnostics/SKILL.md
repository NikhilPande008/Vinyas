---
name: bearing-acoustic-diagnostics
description: Diagnoses CNC spindle bearing outer-race spalling, inner-race pitting, lubrication starvation, and regenerative chatter using 48 kHz acoustic emission harmonics (BPFO/BPFI) and ISO-10816-3 vibration velocity thresholds. Trigger this skill when scenario_key is LINE_B_CNC or when acoustic/vibration sensor telemetry exceeds 3.5 mm/s RMS or exhibits 4.2 kHz harmonic peaks.
---

# CNC Spindle Bearing Acoustic Diagnostics (`bearing-acoustic-diagnostics`)

## Domain Scope
Applies to high-speed CNC machining centers (Makino, Haas, Jyoti, BFW) machining automotive transmission housings and steering knuckles in Pune Chakan/Bhosari plants.

## Diagnostic Workflow
1. **Harmonic & Envelope Analysis:**
   - Inspect the `2.0 kHz – 8.0 kHz` structural resonance band for repetitive impact modulation at the **Ball Pass Frequency Outer Race (BPFO)** or **Inner Race (BPFI)**.
   - Compare overall vibration velocity (`mm/s RMS`) against **ISO-10816-3 Group 2** rigid foundation limits.
2. **Fault Classification:**
   - **Outer-Race Micro-Spall (`4.1–4.3 kHz` peak + `> 4.5 mm/s RMS`):** High-frequency demodulated envelope spikes coupled with spindle nose temperature rise (`> 58 °C`).
   - **Regenerative Tool Chatter:** High coherence between acoustic emission and spindle motor current ripple without bearing cage sidebands.
3. **Prescribed Maintenance Action:**
   - Execute controlled feed-hold at end of current G-code block (`M01`).
   - Inspect angular contact bearing pair (`7014C / P4` precision class) preload and air-oil mist lubricator pressure (`0.35 MPa`).
   - Replace degraded front bearing cartridge and verify spindle runout `< 0.003 mm` TIR before releasing production.
