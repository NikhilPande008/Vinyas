---
name: bearing-acoustic-diagnostics
description: Diagnoses CNC spindle bearing outer-race faults, shaft imbalance, and transient impacts using 48 kHz vibration envelope analysis (BPFO/BPFI) and ISO 20816-3 reference severity zones.
---

# CNC Spindle Bearing Acoustic Diagnostics (`bearing-acoustic-diagnostics`)

## Domain Scope
Applies to high-speed CNC machining centers machining automotive housings and knuckles. Note: rolling-element bearings sit inside the assembled spindle housing, so the camera cannot see raceway defects; CNC diagnosis is vibration-led.

## Diagnostic Workflow
1. **Bandpass & Hilbert Envelope Analysis:**
   - Bandpass-filter the 48 kHz vibration signal (`2.0–8.0 kHz`) to isolate the structural resonance carrier (`~4.2 kHz`), demodulate with `|hilbert(x)|`, remove DC, and compute the envelope FFT.
   - For a representative 7014C-class angular-contact bearing (`n=20`, `d=11.1 mm`, `D=90 mm`, `alpha=15°`) at `5400 rpm` (`f_r=90 Hz`), `BPFO ≈ 793 Hz` and `BPFI ≈ 1007 Hz`.
   - Compare overall vibration velocity (`mm/s RMS`, `10–1000 Hz`) against **ISO 20816-3 Group 2** rigid-support reference zones (`A/B 1.4`, `B/C 2.8`, `C/D 4.5 mm/s`; production spindles normally apply OEM-specific limits).
2. **Fault Classification:**
   - **Outer-Race Fault (`OUTER_RACE_FAULT`):** Periodic envelope peak at `BPFO` (`SNR >= 14 dB`) with `2× BPFO` harmonic (`SNR >= 11 dB`), SNR measured against the median envelope spectrum in `50–2,000 Hz` (the same rule as `backend/dsp/envelope.py`; healthy spindles on the mock rig reach up to ~`10.5 dB` at BPFO from noise alone, so lower peaks are not evidence of a fault), typically accompanied by elevated RMS velocity and spindle nose temperature rise (`> 55 °C`).
   - **Shaft Imbalance (`IMBALANCE`):** Elevated `1×` shaft harmonic (`90 Hz`) and Zone C/D velocity without BPFO periodicity.
   - **Transient Impact (Hard Negative):** High kurtosis without BPFO periodicity (e.g., wrench strike) — informational only, do not escalate as a bearing fault.
3. **Prescribed Maintenance Action (Human-Approved):**
   - Recommend QE hold and controlled `M01` feed-hold at end of current G-code block.
   - Inspect angular contact bearing pair (`7014C / P4` precision class) preload and air-oil mist lubricator pressure (`0.35 MPa`).
   - Replace degraded front bearing cartridge (locknut `145 Nm`, drawbar stud `85 Nm`) and verify spindle taper runout `< 0.003 mm` TIR before resuming production.
