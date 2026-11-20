# IPC-A-610 Class 3 Automotive Solder Standards Reference

## 1. Fine-Pitch Gull-Wing Leads (QFP / LQFP / TSSOP)
- **Target Condition (Class 3):**
  - Smooth, concave meniscus wetting at least `75%` of lead heel height.
  - Zero solder bridging or webbing between adjacent leads (`0.4 mm – 0.5 mm` pitch).
- **Defect Condition (Class 3 Reject):**
  - Any electrical short or solder bridge connecting adjacent pins (e.g., Pins 14–16 on MCU U4).
  - Minimum electrical clearance violated (`< 0.13 mm` on uncoated copper pads).

## 2. Reflow Thermal Profile Parameters (SAC305 Lead-Free Paste)
- **Preheat Ramp Rate:** `1.2 °C/s` to `2.0 °C/s` (max `2.5 °C/s` to prevent solder slump bridging).
- **Soak Zone:** `150 °C – 180 °C` for `60 – 90 seconds`.
- **Peak Reflow Temperature:** `238 °C – 245 °C` (`45 – 60 seconds` Time Above Liquidus `217 °C`).
- **Stencil Wipe Interval:** Mandatory underside vacuum wipe every `5 prints` for `0.4 mm` pitch apertures.
