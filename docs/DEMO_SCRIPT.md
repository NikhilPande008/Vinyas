# Vinyas — 3:00 Demo Video Script (`docs/DEMO_SCRIPT.md`)

**Record against:** Live Cloud Run URL (`https://vinyas-ai-65216244490.asia-south1.run.app`).

- **0:00–0:20 | Hook & Honesty Statement**
  Show the clean empty state on screen. State clearly: *"One missed spindle bearing fault or solder bridge can scrap an entire batch. Vinyas is an AI-assisted quality and predictive-maintenance app built with Google AI on Cloud Run. Per the organiser ruling, sensor and camera inputs are simulated and labelled `SIMULATED INPUT`; all DSP and AI decisions are live and unscripted."*
- **0:20–0:55 | Blind CNC Draw → DSP Envelope Analysis → Reveal**
  Select **Line B — CNC Spindle**. Click **Draw random part** → **Inspect part**. Point to the **Tier-1A Hilbert Envelope Spectrum** showing the computed `BPFO ≈ 793 Hz` peak (and `2× BPFO`) demodulated from the `2–8 kHz` resonance band, and note that CNC is vibration-led because the bearing sits inside the spindle. Click **Reveal ground truth** to show the system matched the hidden manifest and updated the session tally.
- **0:55–1:30 | Escalation, Provenance, SOP Guard & Model-BBox Overlay**
  Draw/inspect a PCB or MIG weld defect so Tier-2 runs. Highlight:
  1. Exact `model_id` provenance chip and the **Attempts trace** disclosure.
  2. **Tier-3 Visual Repair Card** showing the bounding box returned by the model (never fixed coordinates).
  3. **SOP-Guarded Repair Steps** (any parameter not in the SOP gets flagged `⚠ value not in SOP`).
  4. **Estimated avoidable loss (assumption-based)** from deterministic code (`₹0` on nominal parts).
- **1:30–1:55 | Vernacular Hands-Free Co-Pilot (`gemini-3.8-live`)**
  Switch language to **हिन्दी** or **मराठी** (switch to **Operator View** to show large text & giant verdict card). Tap **Push to Talk** (or type a Hindi/Marathi question about torque spec) and play the spoken `gemini-3.8-live` audio response over `/api/live-copilot` WebSocket.
- **1:55–2:15 | Human Disposition → Multilingual Work Order**
  Record a human disposition (`HOLD`, role `QE`) — note that the work-order form is locked until a human decides. Enter a Hindi maintenance note (`तुरंत स्पिंडल रोकें, SP-7014C-P4S बदलना है`) and click **Log work order**; show Gemini extracting `part_code`, `shift_priority`, `required_spares`, and `SLA RISK`.
- **2:15–2:40 | 10-Part Batch Line Run (Measured Token Accounting)**
  In **Engineer View**, click **Run 10-part batch**. Show real measured counts: parts inspected, escalated, gated tokens vs estimated cloud-only tokens, and measured token saving %.
- **2:40–3:00 | Measured Eval, Limitations & Close**
  Briefly flash `eval/RESULTS.md` (with its simulated-data header) and state honest limitations (simulated inputs, demo SQLite store, plant validation next).
