---
name: maintenance-work-order
description: Structures shop-floor maintenance work orders, calculates Pune Tier-2/3 automotive line scrap and downtime savings in INR, and enriches operator notes with spare part SKUs, shift priority, and OEM SLA breach flags. Trigger this skill when diagnosing chassis weld porosity (LINE_C_WELD), calculating financial impact, or generating AlloyDB work orders.
---

# Maintenance Work Order & Weld/Line Cost Triage (`maintenance-work-order`)

## Domain Scope
Applies to discrete manufacturing work order creation, robotic MIG chassis weld seam porosity remediation, and financial ROI quantification across Pune automotive suppliers.

## Diagnostic & Work Order Enrichment Rules
1. **Robotic MIG Weld Porosity (`LINE_C_WELD`):**
   - When thermal camera / optical frame detects surface pinholes or wormhole porosity along a tubular chassis subframe weld:
   - Check Argon/CO2 (`82%/18%`) shielding gas flow rate (`nominal 15–18 L/min`; porosity occurs below `9 L/min` or when spatter clogs the diffuser nozzle).
   - Check wire feed speed stability and contact tip (`1.2 mm CuCrZr`) wear.
2. **In-Database Work Order Structuring (`AI.EXTRACT` & `AI.IF`):**
   - Extract `part_code` (e.g., `SP-7014C-P4`, `NOZ-MIG-16MM`, `STENCIL-QFP-04`), `shift_priority` (`P1_IMMEDIATE`, `P2_CURRENT_SHIFT`, `P3_PLANNED_PM`), and `required_spares`.
   - Flag `sla_critical_flag = true` whenever line stoppage risk or Tier-1 OEM shipment SLA breach is detected.
3. **Financial Impact Formula (`scripts/calc_downtime_cost.py`):**
   - Computes avoided batch scrap + prevented unplanned downtime value in INR (`₹`).
