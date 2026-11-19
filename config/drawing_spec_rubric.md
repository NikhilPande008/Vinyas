# Vinyas Drawing Specification & IATF 16949 14-Reference Visual Inspection Rubric

**Document ID:** `VINYAS-DRAWING-SPEC-RUBRIC-2026`  
**Prepared By:** Team Vinyas (Nikhil Pande & Ravi Mule) — Pune-Chakan Precision Automotive Corridor  
**Applicable Drawings:** Differential Carrier Housing (`AlSi9Cu3(Fe)` / `ADC12` HPDC) & Commercial Steering Knuckle Bore (`EN-GJS-500-7` SG Iron)  
**Standards Compliance:** IATF 16949:2016 Clause 8.5.1.1 (Control Plan), Clause 8.6.2 (Layout Inspection), ISO 21920 Surface Texture, ISO 1302 Roughness Symbols.

---

## 1. Dual-Modality `cycle_id` Adjudication Architecture

Every post-cycle optical frame captured on the cross-polarized, air-purged V-block inspection station is strictly linked via `cycle_id` to its in-cycle `InCycleTelemetrySummary` recorded at `48 kHz` Stereo (Channel 0: Contact Piezo Structure-Borne Vibration; Channel 1: Single-Conductor Split-Core Motor Current Transformer).

1. **Primary Chatter Confirmation (`REF-04`, `REF-05`, `REF-06`):**
   When the optical inspection identifies periodic chatter marks (`REF-04`), exit rollover burrs (`REF-05`), or linear chipping score lines (`REF-06`), the system cross-checks the linked `cycle_id` in-cycle vibration band power ratio (`2000-8000 Hz`), spectral crest factor, and Hilbert Envelope Magnitude-Squared Coherence. Elevated high-frequency structure-borne energy confirms an in-cycle CNC tool instability event requiring operator Feedrate Override (`[70%, 110%]`) and Spindle Speed Override (`[80%, 115%]`) adjustment via the deterministic physics solver.
2. **Upstream Foundry Porosity Chargeback Proof (`REF-10`, `REF-11`):**
   When face-milling or fine-boring uncovers clustered subsurface gas pinholes (`REF-10`) or refractory sand/slag inclusions (`REF-11`) while the linked `cycle_id` telemetry proves clean, low-vibration cutting (`2000-8000 Hz` band power ratio nominal, chatter flag false, peak vibration RMS within baseline), the defect is mathematically proven to originate at the upstream foundry rather than on the CNC spindle. Vinyas immediately classifies the component as `FOUNDRY_POROSITY_CHARGEBACK` and binds the `cycle_id` telemetry summary and raw optical frame `SHA-256` digest into a Cloud KMS (`EC_SIGN_P256_SHA256`) signed QA / Foundry Chargeback Certificate recovering `INR 14,000` per scrapped casting.
3. **Benign Shop-Floor Artifact Suppression (`REF-12`, `REF-13`, `REF-14`):**
   Translucent residual coolant beads (`REF-12`), detached loose swarf particles (`REF-13`), and zero-depth graphite streaks on nodular cast iron (`REF-14`) must never trigger false casting rejects. Benign artifacts trigger either a secondary `0.5 s` air-knife puff or clean pass disposition.

---

## 2. Canonical 14-Reference Visual Taxonomy (`REF-01` through `REF-14`)

### Class A — Golden Master References (`NONE_GOLDEN` -> `passed_iatf_16949 = true`)

* **`REF-01` — Golden Master: Precision Bore & Sealing Datum Face**
  * **Drawing Requirement:** Concentric isotropic fine-boring or face-milling lay with arithmetic mean roughness `Ra <= 1.2 um` (`Rz <= 6.3 um`) and crisp `0.5 mm x 45 deg` chamfer edge with zero metallic lip.
  * **Linked `cycle_id` Signature:** Nominal tooth-passing spectrum, `2000-8000 Hz` vibration ratio below chatter floor, zero instability trigger.
  * **Disposition:** `PASS` — Issue ECDSA P-256 / Cloud KMS Signed QA Certificate.

* **`REF-02` — Golden Master: Tapped Thread Boss & Counterbore (`M12 x 1.75 - 6H`)**
  * **Drawing Requirement:** Complete thread flanks on first three lead pitches, zero exit tear-out, clean minor diameter counterbore free of collapsed crests.
  * **Linked `cycle_id` Signature:** Symmetric rigid-tapping load reversal with zero torsional stick-slip burst.
  * **Disposition:** `PASS` — Issue ECDSA P-256 / Cloud KMS Signed QA Certificate.

* **`REF-03` — Golden Master: Cross-Polarized Dry Alloy Reflectance**
  * **Drawing Requirement:** Homogeneous matte silver-grey metallic reflectance on `AlSi9Cu3` or uniform pearlitic grey on `EN-GJS-500-7` under `90 deg` cross-polarized dome lighting (`0.4 um <= Ra <= 1.25 um`), verifying zero thermal oxidation and complete coolant purge.
  * **Disposition:** `PASS` — Issue ECDSA P-256 / Cloud KMS Signed QA Certificate.

---

### Class B — True CNC Machining Defects (`CHATTER_SCAR_REJECT` & `MICRO_BURR_REJECT` -> `passed_iatf_16949 = false`)

* **`REF-04` — True Defect: Regenerative Chatter Witness Marks (`CHATTER_SCAR_REJECT`)**
  * **Drawing Violation:** Periodic sinusoidal or fish-scale wave patterns (`0.4 mm to 1.2 mm` spatial wavelength) along the internal bearing bore wall or planar gasket face; `Ra` degraded to `2.8 um - 6.5 um` (violating `1.6 um` upper specification limit).
  * **Linked `cycle_id` Signature:** Sustained `2000-8000 Hz` structure-borne vibration dominance (often `3.8-4.5 kHz`) with high spectral crest factor, boosted by Ch 0 / Ch 1 Hilbert Envelope Coherence (`>= 0.72`).
  * **Mandatory Remediation:** Quarantine casting; apply deterministic physics control solution (Operator Feedrate Override dial within `[70%, 110%]`, Spindle Speed Override dial within `[80%, 115%]`, chip-load ratio strictly clamped in `[0.65, 1.15]`), and index carbide insert to fresh corner at `M01` hold.

* **`REF-05` — True Defect: Exit Rollover Burr (`MICRO_BURR_REJECT`)**
  * **Drawing Violation:** Continuous plastically deformed metallic lip (`height > 0.15 mm`, `root thickness > 0.08 mm`) hanging over the exit edge of a milled face or intersecting oil gallery port (`Ra 1.8 - 4.2 um` along rim).
  * **Linked `cycle_id` Signature:** Progressive flank wear elevation in `2000-8000 Hz` vibration RMS and rising Z-axis cutting load over consecutive cycles.
  * **Mandatory Remediation:** Route casting to deburring rework; index insert corner at `M01` optional stop.

* **`REF-06` — True Defect: Insert Micro-Chipping Score Line (`CHATTER_SCAR_REJECT`)**
  * **Drawing Violation:** Singular deep linear score gouge, uncut ridge, or stepped helical groove (`depth > 25 um`, `Rt > 25.0 um`) across critical O-ring or gasket sealing face.
  * **Linked `cycle_id` Signature:** Abrupt broadband impulse exceeding `4.5 G` RMS accompanied by sustained post-fracture high-frequency rubbing.
  * **Mandatory Remediation:** Quarantine casting; lock out cycle start until fractured insert is replaced and verified.

* **`REF-07` — True Defect: Thermal Oxidation Glaze / Burn (`CHATTER_SCAR_REJECT`)**
  * **Drawing Violation:** Straw-yellow, bronze, or bluish temper oxide tint band across machined steel or cast-iron surface indicating metallurgical surface tempering (`Ra 1.6 - 3.8 um`).
  * **Linked `cycle_id` Signature:** Elevated high-frequency friction band energy with low coolant flow thermal drift.
  * **Mandatory Remediation:** Reject casting for metallurgical audit; verify flood coolant nozzle pressure (`>= 8 bar`).

* **`REF-08` — True Defect: Built-Up Edge (BUE) Tear (`MICRO_BURR_REJECT`)**
  * **Drawing Violation:** Jagged micro-craters and cold-welded aluminum/iron fragments torn and re-deposited along tool path (`Ra 2.4 - 5.2 um`).
  * **Linked `cycle_id` Signature:** Erratic mid-band stick-slip acoustic modulation under suboptimal cutting velocity.
  * **Mandatory Remediation:** Hold machine; increase spindle speed within `[80%, 115%]` control window and verify coolant concentration (`7%-9%` Brix).

* **`REF-09` — True Defect: Axial Feed-Dwell Witness Line (`CHATTER_SCAR_REJECT`)**
  * **Drawing Violation:** Single distinct axial or circumferential step mark (`depth 8 - 20 um`) where cutting edge paused while engaged in bore finishing pass (`Ra 1.9 - 3.4 um`).
  * **Linked `cycle_id` Signature:** Unscheduled mid-cut feed interruption or servo stutter.
  * **Mandatory Remediation:** Route part to CMM roundness/cylindricity audit; keep machine in `DAY1_ANDON_ONLY` / `M01` end-of-block advisory mode during fine finishing passes.

---

### Class C — Upstream Foundry Material Defects (`FOUNDRY_POROSITY_CHARGEBACK` -> `passed_iatf_16949 = false`)

* **`REF-10` — Material Defect: Subsurface Hydrogen / Shrinkage Porosity (`FOUNDRY_POROSITY_CHARGEBACK`)**
  * **Drawing Violation:** Clustered circular or vermicular dark pinholes (`diameter 0.3 mm to 2.0 mm`) exposed only after face-milling removes the top casting skin, while surrounding machined lay remains clean (`Ra <= 1.3 um`).
  * **Linked `cycle_id` Proof:** Clean in-cycle vibration telemetry (`stage_a_state == GREEN_NOMINAL`, low band power ratio, low coherence) proving zero CNC chatter during removal.
  * **Mandatory Remediation:** Do NOT adjust CNC offsets or scrap carbide inserts. Quarantine casting into Supplier Chargeback Bin and issue signed KMS Chargeback Certificate (`+INR 14,000` recovery).

* **`REF-11` — Material Defect: Sand / Oxide Slag Inclusion (`FOUNDRY_POROSITY_CHARGEBACK`)**
  * **Drawing Violation:** Irregular dark non-metallic refractory pocket embedded in casting wall, optionally with a short trailing tool abrasion scratch.
  * **Mandatory Remediation:** Quarantine casting for Foundry Chargeback AND inspect tool tip edge for abrasive chipping before resuming production.

---

### Class D — Benign Shop-Floor Artifacts (`HARMLESS_OIL_DROPLET` & `NONE_GOLDEN` -> `passed_iatf_16949 = true`)

* **`REF-12` — Benign Artifact: Residual Semi-Synthetic Coolant Bead (`HARMLESS_OIL_DROPLET`)**
  * **Optical Signature:** Translucent hemispherical fluid droplet with smooth refractive meniscus atop uniform `REF-01` tool lay (`Ra <= 1.2 um`).
  * **Disposition:** `PASS` (False-positive suppressed). Log air-knife coalescing filter inspection if recurring.

* **`REF-13` — Benign Artifact: Loose Unattached Swarf Particle (`HARMLESS_OIL_DROPLET`)**
  * **Optical Signature:** Detached curled metal chip resting on surface with visible shadow gap and zero metallurgical bond to parent edge.
  * **Disposition:** `PASS` after secondary `0.5 s` air-knife blow-off. Never confuse with attached rollover burr (`REF-05`).

* **`REF-14` — Benign Artifact: Nodular Graphite Lubrication Smudge (`NONE_GOLDEN`)**
  * **Optical Signature:** Faint matte dark-grey streak across machined SG iron face with zero tactile depth (`Ra <= 1.1 um`).
  * **Disposition:** `PASS` (False-positive suppressed). Normal free-graphite smearing during finishing cuts.
