---
name: maintenance-work-order
description: Diagnoses robotic MIG chassis weld seam porosity and spatter, structures maintenance work orders from multilingual operator notes, and computes deterministic assumption-based avoidable loss in INR.
---

# Maintenance Work Order & MIG Weld Triage (`maintenance-work-order`)

## Domain Scope
Applies to robotic MIG chassis subframe weld seam inspection (AWS D1.1-style visual porosity criteria for demo; production follows OEM weld specification) and structured work-order creation.

## Diagnostic & Work Order Rules
1. **Robotic MIG Weld Porosity (`POROSITY_GAS_LOSS`):**
   - Look for clustered dark surface pits/wormholes along the weld bead.
   - Check Argon/CO2 (`82% / 18%`) shielding gas flow rate (`nominal 15–20 L/min`; porosity risk rises sharply below `12 L/min` due to spatter occlusion in the `16 mm` conical nozzle).
   - Distinguish cosmetic spatter beads beside the seam (`SPATTER_COSMETIC`, nominal gas flow) from true seam porosity.
   - Recommend QE disposition (`HOLD` / `REWORK`): grind out porous bead to sound metal, replace clogged nozzle (`NOZ-MIG-16MM`) and `1.2 mm` CuCrZr contact tip, restore gas flow to `16.5 L/min`, torque torch swan-neck nut to `22 Nm`.
2. **Work Order Structuring:**
   - Extract `part_code`, `shift_priority` (`P1_IMMEDIATE`, `P2_CURRENT_SHIFT`, `P3_PLANNED_PM`), `required_spares`, and `sla_risk` from English, Hindi, or Marathi operator notes.
   - A work order may be logged only after a QE or Supervisor records a disposition (`HOLD`, `REWORK`, or `SCRAP`).
3. **Deterministic Economics (`backend/services/economics.py`):**
   - Computes assumption-based estimated avoidable loss in INR (`₹0` for nominal parts). Never let an LLM invent financial amounts.
