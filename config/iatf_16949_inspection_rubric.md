# IATF 16949:2016 Automotive Production Part Approval Process (PPAP) Optical & Acoustic-Electrical Inspection Rubric

**Document Control ID:** `IATF-CHAKAN-AOI-RUBRIC-V2.1`
**Applicable Components:** CNC-Machined High-Pressure Die Cast Aluminum (`AlSi9Cu3(Fe)` / `ADC12`) Differential Carrier Housings, Steering Knuckle Bores, and Spheroidal Graphite (`SG Iron EN-GJS-500-7`) Heavy Commercial Hubs.
**Governing Quality Standards:** IATF 16949:2016 Clause 8.5.1.1 (Control Plan), Clause 8.6.2 (Layout Inspection and Functional Testing), ISO 4287 / ISO 21920 Geometrical Product Specifications (Surface Texture), and ISO 1302 Surface Roughness Indication Standards.

---

## 1. Purpose & Dual-Modality Adjudication Protocol

This mandatory inspection rubric governs automated post-cycle optical verification (`Nano Banana Pro` / `gemini-2.5-flash` Context Cache) in conjunction with in-cycle hardware-synchronized `48 kHz` Stereo Acoustic Emission (`AE`) and Split-Core Motor Current Transformer (`CT`) telemetry.

Every machined casting unloaded onto the cross-polarized, `6-bar` air-knife V-block fixture must be classified against the 14 canonical visual reference tokens (`REF-01` through `REF-14`) cached inside the active context window. The inspection engine must never evaluate visual surface anomalies in isolation from the cycle's physical cutting telemetry:

1. **Acoustic-Electrical Corroboration Rule:** A surface defect attributed to CNC tool instability (`REF-04` Regenerative Chatter, `REF-05` Exit Rollover Burr, `REF-06` Insert Chipping Scar) is corroborated when the in-cycle Hilbert Envelope Magnitude-Squared Coherence between `Ch0` (`2000-8000 Hz` AE carrier) and `Ch1` (`50-400 Hz` CT spindle phase load) exceeded `0.72` within the `30-250 Hz` modulation baseband, or when a transient acoustic RMS spike (`> 2.5 G`) occurred during metal removal.
2. **Upstream Foundry Attribution & Chargeback Rule (`REF-10` & `REF-11`):** When the optical frame exhibits exposed subsurface gas pinholes (`REF-10`) or non-metallic slag cavities (`REF-11`) on a freshly milled datum face, while the in-cycle spindle acoustic RMS (`< 1.8 G`) and Hilbert Envelope Coherence (`< 0.35`) remained nominal throughout the pass, the defect is classified as `FOUNDRY_POROSITY_CHARGEBACK`. The part must be quarantined into the Supplier Chargeback Bin, and the cryptographic `HMAC-SHA256` digest of both the raw optical frame and clean acoustic RMS trace is attached to the Foundry Debit Note.
3. **Benign Shop-Floor Artifact Suppression Rule (`REF-12`, `REF-13`, `REF-14`):** Wet cutting-fluid beads (`REF-12`), unattached curly swarf chips (`REF-13`), and zero-depth free-graphite lubrication streaks on nodular iron (`REF-14`) must never trigger false-positive part scrap. They are suppressed or routed to a secondary `0.5-second` air-knife purge.

---

## 2. Detailed Visual Token Specifications & Dimensional Acceptance Criteria

### 2.1 Golden Master Acceptance Class (`NONE_GOLDEN` -> `passed_iatf_16949 = true`)

* **`REF-01` — Golden Master: Precision Bore & Sealing Datum Face**
  * **Surface Topology:** Uniform, concentric, isotropic fine-boring or face-milling lay with arithmetic mean roughness `Ra <= 1.2 um` (`Rz <= 6.3 um`).
  * **Edge Integrity:** Continuous `0.5 mm x 45 deg` chamfer with crisp transition boundaries, zero attached rollover lip, and zero radial tear-out.
  * **Acoustic Correlation:** Steady tooth-passing harmonic with `AE RMS < 1.9 G`, `CT Ripple Std < 0.28 A`, and envelope coherence `< 0.40`.
  * **Disposition:** `PASS`. Issue Dual-Layer Provenance Certificate (`Cloud KMS HMAC-SHA256` + `SynthID` badge).

* **`REF-02` — Golden Master: Tapped Thread Boss & Counterbore (`M12 x 1.75 - 6H`)**
  * **Surface Topology:** Full, unstripped thread flanks on the first three lead threads; clean minor diameter counterbore without radial burrs or collapsed crests.
  * **Acoustic Correlation:** Symmetric rigid-tapping reversal torque spike with zero torsional stick-slip oscillation.
  * **Disposition:** `PASS`. Issue Dual-Layer Provenance Certificate.

* **`REF-03` — Golden Master: Cross-Polarized Dry Alloy Reflectance**
  * **Optical Signature:** Homogeneous matte silver-grey metallic reflectance on `AlSi9Cu3` or uniform pearlitic grey on `EN-GJS-500-7` under `90-degree` analyzer polarization, confirming zero thermal oxidation and complete flood coolant evacuation.
  * **Surface Roughness Range:** `0.4 um <= Ra <= 1.25 um`.
  * **Disposition:** `PASS`. Issue Dual-Layer Provenance Certificate.

---

### 2.2 True CNC Machining Defect Class (`CHATTER_SCAR_REJECT` & `MICRO_BURR_REJECT` -> `passed_iatf_16949 = false`)

* **`REF-04` — True Defect: Regenerative Chatter Witness Marks (`CHATTER_SCAR_REJECT`)**
  * **Optical Signature:** Periodic sinusoidal or fish-scale wave patterns (`0.4 mm to 1.2 mm` spatial wavelength) visible along the internal bearing bore wall or planar gasket face.
  * **Surface Roughness Range:** `Ra` degraded to `2.8 um - 6.5 um` (violating the `1.6 um` PPAP upper specification limit).
  * **Physical Root Cause:** Carbide insert flank wear land (`VB > 0.22 mm`) or excessive spindle overhang exciting structural regenerative chatter around `4,210 Hz` phase-locked with `68.5 Hz` motor current sidebands.
  * **Mandatory Remediation:** Reject/Rework part; command `Day-1 Feedrate Override Dial` reduction to `85%` (PPAP safe window `70%-110%`), apply Supervisor `M01` manual Z-wear offset (`+10.0 um to +15.0 um`), and index Tool `T03` to fresh Corner `#2`.

* **`REF-05` — True Defect: Plastically Deformed Exit Rollover Burr (`MICRO_BURR_REJECT`)**
  * **Optical Signature:** Continuous raised metallic lip or jagged crown (`height > 0.15 mm`, `root thickness > 0.08 mm`) hanging over the exit edge of a milled slot or cross-drilled oil gallery port.
  * **Surface Roughness Range:** `Ra` between `1.8 um` and `4.2 um` near exit boundary.
  * **Physical Root Cause:** Dull cutting edge radius causing work-material ploughing rather than clean shear cleavage at tool exit.
  * **Mandatory Remediation:** Route casting to manual deburring rework station; mandate immediate carbide insert corner indexing at `M01` stop.

* **`REF-06` — True Defect: Catastrophic Insert Micro-Chipping Score Line (`CHATTER_SCAR_REJECT`)**
  * **Optical Signature:** Singular deep linear gouge, raised uncut ridge, or stepped helical groove (`depth > 25 um`) scoring the precision sealing face.
  * **Surface Roughness Range:** Local profile peak-to-valley `Rt > 25.0 um`, `Ra > 4.5 um`.
  * **Physical Root Cause:** Brittle fracture of the carbide insert nose radius triggered by a hard intermetallic inclusion or thermal shock.
  * **Mandatory Remediation:** Quarantine casting; lock out cycle start until operator replaces fractured insert and verifies tool setter zero.

* **`REF-07` — True Defect: Thermal Oxidation Glaze & Workpiece Burn (`CHATTER_SCAR_REJECT`)**
  * **Optical Signature:** Iridescent straw-yellow, bronze, or bluish-purple temper oxide discoloration band across the machined track, accompanied by glazed micro-cracking.
  * **Surface Roughness Range:** `Ra` `1.6 um - 3.8 um` with metallurgical surface hardness alteration.
  * **Physical Root Cause:** Blocked flood-coolant nozzle, air-locked coolant pump, or cutting velocity `Vc` exceeding carbide grade thermal threshold.
  * **Mandatory Remediation:** Reject casting for metallurgical audit; inspect coolant nozzle alignment and pressure switch (`>= 8 bar`).

* **`REF-08` — True Defect: Built-Up Edge (BUE) Smear & Adhesive Crater Tear (`MICRO_BURR_REJECT`)**
  * **Optical Signature:** Bright, jagged micro-craters with cold-welded aluminum or cast-iron fragments periodically torn and redeposited along the direction of cut.
  * **Surface Roughness Range:** `Ra` `2.4 um - 5.2 um`.
  * **Physical Root Cause:** Insufficient surface cutting speed or degraded emulsion lubricity causing chip stagnation on the tool rake face.
  * **Mandatory Remediation:** Hold machine; increase spindle speed or adjust feedrate override within the upper PPAP window (`102%-108%`) and verify coolant refractometer Brix concentration (`7%-9%`).

* **`REF-09` — True Defect: Axial Feed-Dwell Witness Line (`CHATTER_SCAR_REJECT`)**
  * **Optical Signature:** Distinct axial or circumferential witness step (`depth 8 um - 20 um`) marking the exact locus where the cutting edge dwelled against the rotating or stationary bore wall.
  * **Surface Roughness Range:** `Ra` `1.9 um - 3.4 um` across the dwell transition.
  * **Physical Root Cause:** Uncoordinated mid-pass feed hold or servo drive velocity droop during finishing cut.
  * **Mandatory Remediation:** Route part to Coordinate Measuring Machine (`CMM`) cylindricity audit; ensure edge controller operates in `M01` End-of-Block advisory mode during finishing passes.

---

### 2.3 Upstream Foundry Material Defect Class (`FOUNDRY_POROSITY_CHARGEBACK` -> `passed_iatf_16949 = false`)

* **`REF-10` — Material Defect: Subsurface Hydrogen / Shrinkage Porosity Cluster (`FOUNDRY_POROSITY_CHARGEBACK`)**
  * **Optical Signature:** Clustered circular or vermicular dark pinholes (`diameter 0.3 mm to 2.0 mm`) with smooth interior walls exposed only after the top `1.5 mm` casting skin is removed by face milling. Surrounding machined tool lay remains smooth (`Ra <= 1.3 um`).
  * **Acoustic-Electrical Proof:** In-cycle `AE RMS` and `CT Ripple` remained completely nominal (`coherence < 0.30`), proving the CNC machine cut cleanly without vibration.
  * **Mandatory Remediation:** Do NOT alter CNC offsets or scrap tooling. Quarantine casting to the Foundry Supplier Chargeback pallet and attach the signed `HMAC-SHA256` telemetry certificate to recover casting material and machining value (`INR 14,000`).

* **`REF-11` — Material Defect: Refractory Sand / Oxide Slag Inclusion (`FOUNDRY_POROSITY_CHARGEBACK`)**
  * **Optical Signature:** Irregular, non-metallic matte black or refractory pocket embedded in the casting matrix, often accompanied by a short directional comet-tail scratch where the hard inclusion abraded the carbide insert tip.
  * **Mandatory Remediation:** Quarantine casting for Foundry Supplier Chargeback AND command operator to inspect Tool `T01`/`T03` cutting edge for abrasive notch wear before starting the next part.

---

### 2.4 Benign Shop-Floor Artifact Class (`HARMLESS_OIL_DROPLET` & `NONE_GOLDEN` -> `passed_iatf_16949 = true`)

* **`REF-12` — Benign Artifact: Residual Semi-Synthetic Coolant Bead (`HARMLESS_OIL_DROPLET`)**
  * **Optical Signature:** Translucent hemispherical fluid droplet or thin meniscus film with soft refractive edges resting atop an otherwise uniform `REF-01` tool lay (`Ra <= 1.2 um`).
  * **Disposition:** `PASS` (False-positive suppressed). Do not reject part; log pneumatic air-knife coalescing filter check if droplet frequency exceeds `5%` of cycles.

* **`REF-13` — Benign Artifact: Unattached Loose Swarf Particle (`HARMLESS_OIL_DROPLET`)**
  * **Optical Signature:** Detached, curled metallic chip resting loosely on the planar face with a distinct shadow gap and zero metallurgical bond to the parent casting edge.
  * **Disposition:** `PASS` after secondary `0.5-second` air-knife purge. Never classify an unattached chip as an exit rollover burr (`REF-05`).

* **`REF-14` — Benign Artifact: Nodular Graphite Lubrication Smudge (`NONE_GOLDEN`)**
  * **Optical Signature:** Faint matte dark-grey streak across a machined spheroidal graphite (`SG`) iron face with zero interferometric or tactile depth (`Ra <= 1.1 um`).
  * **Disposition:** `PASS`. Normal free-graphite smearing during dry or minimum-quantity-lubrication (`MQL`) finishing passes.
