---
name: pcb-defect-triage
description: Diagnoses automotive SMT PCB assembly anomalies including fine-pitch QFP solder bridges, tombstoning, cold solder joints, and BGA thermal voiding under IPC-A-610 Class 3 automotive standards. Trigger this skill when scenario_key is LINE_A_PCB or when inspecting optical PCB surface-mount assembly defects.
---

# Automotive PCB Defect Triage (`pcb-defect-triage`)

## Domain Scope
Applies to Pune Tier-2/3 automotive electronic control unit (ECU), BMS, and cluster PCB SMT reflow lines operating under **IPC-A-610 Class 3 (High-Performance/Automotive)** tolerances.

## Diagnostic Workflow
1. **Optical Callout Localization:** Identify bridging across fine-pitch leads (`<= 0.5 mm` pitch QFP/SOIC), insufficient wetting, or solder ball spatter.
2. **Root-Cause Correlation:**
   - **Solder Bridge across QFP Pins:** Check stencil aperture paste release, squeegee pressure (`> 1.2 kg/cm`), or reflow preheat ramp rate exceeding `2.5 °C/sec` causing flux outgassing slump.
   - **Tombstoning / Manhattan Effect:** Check uneven thermal mass across passive pads or pick-and-place nozzle Z-axis offset.
3. **Prescribed Rework & Line Action:**
   - Isolate affected PCB lot and perform hot-air/micro-iron desoldering wick rework with no-clean ROL0 flux.
   - Inspect under 20x stereo microscope to confirm minimum `0.15 mm` electrical clearance.
   - Trigger underside stencil wipe cycle and recalibrate reflow Zone 3–5 thermal profile (`242 °C` peak, `55 sec` Time Above Liquidus).
