---
name: pcb-defect-triage
description: Diagnoses automotive SMT PCB assembly anomalies including fine-pitch QFP solder bridges, insufficient solder, and cosmetic flux residue glare under IPC-A-610 Class 3 automotive acceptability standards.
---

# Automotive PCB Defect Triage (`pcb-defect-triage`)

## Domain Scope
Applies to automotive ECU/BMS SMT reflow lines operating under **IPC-A-610 Class 3** acceptability criteria for SAC305 lead-free assemblies.

## Diagnostic Workflow
1. **Optical Inspection:**
   - **Solder Bridge (`SOLDER_BRIDGE`):** Conductive solder fillet connecting two or more adjacent fine-pitch QFP leads. Correlate with reflow preheat ramp (`> 3.0 °C/s` outside `1.0–3.0 °C/s` SAC305 window) or stencil underside paste slump.
   - **Insufficient Solder (`INSUFFICIENT_SOLDER`):** Starved heel/toe fillet on one or more QFP pads.
   - **Flux Residue Glare (Hard Negative):** Specular sheen between leads without conductive solder bridging — acceptable if continuity/clearance is intact.
2. **Prescribed Rework & Line Action (Human-Approved):**
   - Recommend QE hold and ESD rework station inspection.
   - Apply ROL0 no-clean flux and wick excess SAC305 solder using `1.0 mm` copper desoldering braid at `330 °C`.
   - Verify `> 0.15 mm` inter-lead clearance at `20x` microscope inspection.
   - Trigger stencil underside vacuum wipe and bring reflow profile within SAC305 window (`1–3 °C/s` preheat ramp, `235–250 °C` peak, `45–90 s` Time Above Liquidus).
