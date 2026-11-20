"""Process telemetry synthesis for PCB SMT reflow and MIG weld lines (Mock Rig v2).

Typical process windows (cited in docs/ASSUMPTIONS.md):
- SAC305 Reflow: preheat ramp 1.0-3.0 C/s, peak 235-250 C, TAL 45-90 s
- MIG Weld (82% Ar / 18% CO2): shielding gas 15-20 L/min, arc voltage 20-24 V, wire feed 7.5-9.5 m/min
"""

from __future__ import annotations

from typing import Any
import numpy as np


def generate_pcb_telemetry(defect_class: str, rng: np.random.Generator) -> dict[str, Any]:
    """Generate SAC305 reflow telemetry with realistic overlap so visual inspection matters."""
    if defect_class == "SOLDER_BRIDGE":
        # ~70% show elevated ramp rate (>3.0 C/s), ~30% stay inside window so optical gate is essential
        if rng.random() < 0.70:
            ramp = float(rng.uniform(3.15, 4.10))
            peak = float(rng.uniform(246.0, 255.0))
        else:
            ramp = float(rng.uniform(2.30, 2.95))
            peak = float(rng.uniform(240.0, 248.5))
        tal = float(rng.uniform(55.0, 88.0))
    elif defect_class == "INSUFFICIENT_SOLDER":
        if rng.random() < 0.65:
            peak = float(rng.uniform(224.0, 233.5))
            tal = float(rng.uniform(32.0, 43.0))
        else:
            peak = float(rng.uniform(236.0, 243.0))
            tal = float(rng.uniform(46.0, 62.0))
        ramp = float(rng.uniform(1.10, 2.20))
    else:
        # NOMINAL or FLUX_RESIDUE_GLARE: inside window (some near edges)
        ramp = float(rng.uniform(1.15, 2.85))
        peak = float(rng.uniform(236.5, 249.0))
        tal = float(rng.uniform(47.0, 86.0))

    return {
        "vibration_khz": round(float(rng.uniform(0.25, 0.55)), 2),
        "vibration_rms_mms": round(float(rng.uniform(0.45, 1.05)), 2),
        "temperature_c": round(peak, 1),
        "line_speed_rpm": int(rng.integers(1150, 1260)),
        "shielding_gas_lpm": None,
        "reflow_ramp_c_per_s": round(ramp, 2),
        "reflow_peak_c": round(peak, 1),
        "reflow_tal_s": round(tal, 1),
    }


def generate_weld_telemetry(defect_class: str, rng: np.random.Generator) -> dict[str, Any]:
    """Generate MIG weld cell telemetry (82% Ar / 18% CO2)."""
    if defect_class == "POROSITY_GAS_LOSS":
        gas = float(rng.uniform(5.2, 10.8))
        arc_v = float(rng.uniform(24.5, 27.8))
        wire = float(rng.uniform(7.6, 9.4))
        temp = float(rng.uniform(295.0, 345.0))
    else:
        # NOMINAL or SPATTER_COSMETIC
        gas = float(rng.uniform(15.2, 19.6))
        arc_v = float(rng.uniform(20.4, 23.6))
        wire = float(rng.uniform(7.8, 9.2))
        temp = float(rng.uniform(255.0, 290.0))

    return {
        "vibration_khz": round(float(rng.uniform(0.60, 1.20)), 2),
        "vibration_rms_mms": round(float(rng.uniform(1.05, 2.10)), 2),
        "temperature_c": round(temp, 1),
        "line_speed_rpm": int(rng.integers(1780, 1920)),
        "shielding_gas_lpm": round(gas, 1),
        "arc_voltage_v": round(arc_v, 1),
        "wire_feed_m_per_min": round(wire, 1),
    }
