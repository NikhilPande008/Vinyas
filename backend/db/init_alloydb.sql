-- ============================================================================
-- Vinyas — AlloyDB Express (PostgreSQL 18) Initialization & Seed DDL
-- Follows `.agents/skills/ops-db-guardrails/SKILL.md`:
--   1. All table & column names strictly snake_case
--   2. Mandatory primary key `id` on every table
--   3. Idempotent `CREATE EXTENSION IF NOT EXISTS` & `CREATE TABLE IF NOT EXISTS`
--   4. ScaNN cosine vector index (`alloydb_scann`) on `equipment_sops(embedding)`
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

DO $$ BEGIN
    CREATE EXTENSION IF NOT EXISTS alloydb_scann;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'alloydb_scann extension not installed on this PostgreSQL host; standard pgvector fallback active';
END $$;

DO $$ BEGIN
    CREATE EXTENSION IF NOT EXISTS google_ml_integration;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'google_ml_integration extension not enabled; Python AI.EXTRACT/AI.IF fallback active';
END $$;

-- 1. Equipment SOPs Table (Grounded with 768-D embeddings for ScaNN retrieval)
CREATE TABLE IF NOT EXISTS equipment_sops (
    id TEXT PRIMARY KEY,
    machine_type TEXT NOT NULL,
    fault_code TEXT NOT NULL,
    title TEXT NOT NULL,
    sop_markdown TEXT NOT NULL,
    torque_spec TEXT NOT NULL,
    embedding vector(768) NOT NULL
);

-- 2. Inspection Incidents Ledger
CREATE TABLE IF NOT EXISTS inspection_incidents (
    id TEXT PRIMARY KEY,
    scenario_key TEXT NOT NULL,
    line_name TEXT NOT NULL,
    tier1_status TEXT NOT NULL,
    defect_class TEXT NOT NULL,
    severity TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    scrap_saved_inr INTEGER NOT NULL DEFAULT 0,
    inference_mode TEXT NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Maintenance Work Orders (Enriched via AlloyDB AI.EXTRACT() & AI.IF())
CREATE TABLE IF NOT EXISTS work_orders (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    operator_notes TEXT NOT NULL,
    extracted_tags_json JSONB NOT NULL,
    sla_critical_flag BOOLEAN NOT NULL DEFAULT FALSE,
    db_ai_mode TEXT NOT NULL DEFAULT 'ALLOYDB_IN_SQL',
    status TEXT NOT NULL DEFAULT 'OPEN',
    scrap_saved_inr INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. ScaNN Vector Index on equipment_sops(embedding)
DO $$ BEGIN
    EXECUTE 'CREATE INDEX IF NOT EXISTS equipment_sops_scann_idx ON equipment_sops USING scann (embedding cosine)';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ScaNN index creation skipped; falling back to standard pgvector cosine distance <=>';
END $$;

-- 5. Seed 6 Realistic Pune Discrete Manufacturing SOPs
INSERT INTO equipment_sops (id, machine_type, fault_code, title, sop_markdown, torque_spec, embedding)
VALUES
(
    'SOP-PUNE-PCB-01',
    'SMT_REFLOW_LINE_A',
    'IPC-610-BRIDGE-QFP',
    'Fine-Pitch QFP Solder Bridge & Stencil Paste Slump Remediation (IPC-A-610 Class 3)',
    '1. Quarantine PCB panel immediately. 2. Apply ROL0 no-clean flux across bridged QFP leads (Pins 14-16) and wick excess SAC305 solder using 1.0mm ESD-safe desoldering braid at 330°C. 3. Verify >0.15mm inter-lead clearance at 20x optical zoom. 4. Trigger DEK stencil underside vacuum wipe and reduce reflow Zone 3 preheat slope from 2.7°C/s to 1.8°C/s.',
    'Squeegee Blade Clamp: 4.5 Nm | Nozzle Chuck: 1.2 Nm',
    array_fill(0.0361::real, ARRAY[768])::vector(768)
),
(
    'SOP-PUNE-CNC-02',
    'CNC_SPINDLE_LINE_B',
    'ISO-10816-BPFO-4210HZ',
    'High-Speed CNC Spindle Angular Contact Bearing Outer-Race Spall & Preload Recovery',
    '1. Execute M01 Feed-Hold at cycle completion; engage spindle pneumatic lock. 2. Confirm 4.21 kHz BPFO acoustic harmonic (>4.5 mm/s RMS Zone D) and nose temperature >58°C. 3. Replace front duplex angular contact bearing set (SKU: SP-7014C-P4S) and flush air-oil mist lines at 0.35 MPa. 4. Verify spindle taper dynamic runout <0.003 mm TIR.',
    'Spindle Bearing Locknut: 145 Nm | Drawbar Retention Stud: 85 Nm',
    array_fill(0.0362::real, ARRAY[768])::vector(768)
),
(
    'SOP-PUNE-WELD-03',
    'MIG_CHASSIS_LINE_C',
    'AWS-D1.1-POROSITY-GAS',
    'Robotic MIG Tubular Chassis Subframe Seam Porosity & Shielding Gas Flow Restoration',
    '1. Halt robotic weld cell #3 after current fixture clamp cycle. 2. Grind out porous 35mm weld bead to clean base metal using 4.5-inch zirconia disc. 3. Clear spatter blockage from 16mm conical gas nozzle (SKU: NOZ-MIG-16MM) and restore 82% Ar / 18% CO2 shielding gas flow from 7.8 L/min to 16.5 L/min. 4. Replace 1.2mm CuCrZr contact tip and re-weld.',
    'MIG Torch Swan-Neck Nut: 22 Nm | Wire Drive Roll Tension: Setting 3.5',
    array_fill(0.0360::real, ARRAY[768])::vector(768)
),
(
    'SOP-PUNE-CAL-04',
    'LASER_CALIBRATION_LINE_D',
    'NOMINAL-BASELINE-PASS',
    'Nominal Reference Calibration & Golden Part Optical/Acoustic Baseline Verification',
    '1. Confirm vibration RMS <1.4 mm/s (ISO-10816 Zone A) and surface geometry within ±0.015 mm GD&T tolerance. 2. Log Tier-1 Edge HEALTHY pass and suppress Tier-2 cloud escalation to conserve 95% token budget.',
    'Fixture Datum Clamp: 35 Nm',
    array_fill(0.0359::real, ARRAY[768])::vector(768)
),
(
    'SOP-PUNE-PCB-05',
    'SMT_REFLOW_LINE_A',
    'IPC-610-BGA-VOID',
    'Automotive ECU Power BGA Thermal Pad Voiding & Nitrogen Reflow O2 PPM Adjustment',
    '1. Inspect 2D X-ray void percentage (>25% reject threshold under IPC-7095 Class 3). 2. Check N2 inert gas flow to maintain <800 ppm O2 in soak/reflow zones. 3. Extend soak duration at 165°C by +15s to allow complete flux volatile outgassing.',
    'Conveyor Rail Lead-Screw Lock: 6.0 Nm',
    array_fill(0.0358::real, ARRAY[768])::vector(768)
),
(
    'SOP-PUNE-CNC-06',
    'CNC_SPINDLE_LINE_B',
    'CHATTER-CARBIDE-INSERT',
    'Finish Boring Bar Regenerative Chatter Suppression & Carbide Insert Indexing',
    '1. Reduce spindle RPM by -12% to exit regenerative lobe and adjust feedrate dial to +5% to maintain nominal chip load. 2. Index CNMG-120408 TiAlN coated carbide insert to fresh cutting corner.',
    'Insert Torx Clamp Screw (M4): 3.8 Nm | Toolholder Pull-Stud: 75 Nm',
    array_fill(0.0357::real, ARRAY[768])::vector(768)
)
ON CONFLICT (id) DO NOTHING;
