-- ============================================================================
-- Production design — NOT deployed in this demo.
--
-- The hosted Cloud Run demo uses SQLite (`backend/db/demo_store.py`) and notes
-- that demo data resets on container restart. This file documents the intended
-- production PostgreSQL + pgvector / AlloyDB schema.
--
-- Embeddings:
--   `embedding vector(768)` matches `gemini-embedding-2` configured with
--   `output_dimensionality = 768`.
--   SOP seed rows intentionally leave `embedding = NULL`; the application
--   populates real embeddings via `gemini-embedding-2` on startup or migration.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS equipment_sops (
    id TEXT PRIMARY KEY,
    machine_type TEXT NOT NULL,
    fault_code TEXT NOT NULL,
    title TEXT NOT NULL,
    sop_markdown TEXT NOT NULL,
    torque_spec TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding vector(768)
);

CREATE INDEX IF NOT EXISTS idx_equipment_sops_embedding_hnsw
    ON equipment_sops USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS inspection_incidents (
    id TEXT PRIMARY KEY,
    line TEXT NOT NULL,
    sample_id TEXT,
    line_name TEXT NOT NULL,
    tier1_status TEXT NOT NULL,
    defect_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    avoidable_loss_inr INTEGER NOT NULL DEFAULT 0,
    inference_mode TEXT NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS incident_dispositions (
    incident_id TEXT PRIMARY KEY REFERENCES inspection_incidents(id),
    decision TEXT NOT NULL CHECK (decision IN ('RELEASE', 'HOLD', 'REWORK', 'SCRAP')),
    role TEXT NOT NULL CHECK (role IN ('QE', 'Supervisor')),
    note TEXT NOT NULL DEFAULT '',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS work_orders (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL REFERENCES incident_dispositions(incident_id),
    machine_id TEXT NOT NULL,
    operator_notes TEXT NOT NULL,
    extracted_tags_json JSONB NOT NULL,
    sla_critical_flag BOOLEAN NOT NULL DEFAULT FALSE,
    extraction_producer TEXT NOT NULL,
    extraction_model_id TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN',
    avoidable_loss_inr INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed SOPs without constant/dummy vectors; application populates `embedding` via gemini-embedding-2.
INSERT INTO equipment_sops (id, machine_type, fault_code, title, sop_markdown, torque_spec, content_hash, embedding)
VALUES
(
    'SOP-PCB-01',
    'SMT_REFLOW_PCB',
    'IPC610-SOLDER-BRIDGE',
    'Fine-Pitch QFP Solder Bridge & Stencil Paste Slump Remediation (IPC-A-610 Class 3)',
    '1. Quarantine PCB panel on ESD rework station. 2. Apply ROL0 flux and wick excess SAC305 solder using 1.0 mm braid at 330 C. 3. Verify >0.15 mm clearance at 20x. 4. Wipe stencil underside and hold preheat ramp within 1.0-3.0 C/s.',
    'Squeegee Blade Clamp: 4.5 Nm | Stencil Frame Lock: 1.2 Nm',
    'seed-v2',
    NULL
),
(
    'SOP-CNC-01',
    'CNC_SPINDLE',
    'ISO20816-BPFO-OUTER-RACE',
    'CNC Spindle Angular-Contact Bearing Outer-Race Fault & Cartridge Replacement',
    '1. Execute M01 feed-hold and lock spindle. 2. Confirm periodic BPFO envelope harmonic (~793 Hz at 5400 rpm, exciting ~4.2 kHz structural resonance). 3. Replace front duplex 7014C P4 bearing set (SKU: SP-7014C-P4S) and flush air-oil mist at 0.35 MPa. 4. Verify runout <0.003 mm TIR.',
    'Spindle Bearing Locknut: 145 Nm | Drawbar Retention Stud: 85 Nm',
    'seed-v2',
    NULL
),
(
    'SOP-WELD-01',
    'MIG_CHASSIS_WELD',
    'MIG-POROSITY-GAS-LOSS',
    'Robotic MIG Chassis Subframe Seam Porosity & Shielding Gas Restoration',
    '1. Interlock weld cell. 2. Grind porous bead to sound metal. 3. Replace clogged 16 mm gas nozzle (SKU: NOZ-MIG-16MM) and 1.2 mm CuCrZr contact tip. 4. Restore 82% Ar / 18% CO2 shielding gas to 15-20 L/min (target 16.5 L/min).',
    'MIG Torch Swan-Neck Nut: 22 Nm | Gas Regulator Nut: 18 Nm',
    'seed-v2',
    NULL
)
ON CONFLICT (id) DO NOTHING;
