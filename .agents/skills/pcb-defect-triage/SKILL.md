---
name: pcb-defect-triage
description: Diagnoses automotive SMT PCB assembly anomalies including fine-pitch QFP solder bridges, insufficient solder, and cosmetic flux residue glare under IPC-A-610 Class 3 automotive acceptability standards.
---

# Automotive PCB Defect Triage (`pcb-defect-triage`)

## Domain Scope
Applies to automotive ECU/BMS SMT reflow lines operating under **IPC-A-610 Class 3** acceptability criteria for SAC305 lead-free assemblies.

## Diagnostic Workflow
1. **Optical Inspection:**
   - **Solder Bridge (`SOLDER_BRIDGE` -> `SOP-PCB-01`):** Bright metallic solder blob or conductive fillet connecting two or more adjacent fine-pitch QFP leads. Correlate with reflow preheat ramp (`> 3.0 °C/s` outside `1.0–3.0 °C/s` SAC305 window) or stencil underside paste slump.
   - **Insufficient Solder (`INSUFFICIENT_SOLDER` -> `SOP-PCB-02`):** Dark, brown, bare, or starved heel/toe fillet on one or more QFP pads with NO metallic bridge joining adjacent leads. Often correlates with low reflow peak (`< 235 °C`) or short Time Above Liquidus (`< 45 s`), or aperture blockage.
   - **Flux Residue Glare (Hard Negative -> `SOP-PCB-03`):** Translucent specular sheen on the green solder mask away from leads without conductive solder bridging — acceptable if `> 0.15 mm` lead clearance is intact.
2. **Prescribed Rework & Line Action (Human-Approved):**
   - Recommend QE hold and ESD rework station inspection.
   - For `SOLDER_BRIDGE` (`SOP-PCB-01`): apply ROL0 no-clean flux, wick excess SAC305 solder using `1.0 mm` copper braid at `330 °C`, verify `> 0.15 mm` inter-lead clearance at `20x`, and run stencil underside vacuum wipe (`1.0–3.0 °C/s` preheat ramp, target `1.8 °C/s`).
   - For `INSUFFICIENT_SOLDER` (`SOP-PCB-02`): check stencil aperture blockage and paste viscosity, verify SAC305 reflow peak `235–250 °C` and Time Above Liquidus `45–90 s`, and touch up starved leads with `0.3 mm` SAC305 wire at `330 °C` using ROL0 flux.
