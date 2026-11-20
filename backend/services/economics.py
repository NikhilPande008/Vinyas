"""Deterministic avoidable-loss calculator (`backend/services/economics.py`).

All constants are documented in `docs/ASSUMPTIONS.md` as team assumptions (unvalidated
with plants unless cited). Financial estimates NEVER come from an LLM.
Nominal / NO_DEFECT_FOUND parts always return INR 0 and 0 minutes.
"""

from __future__ import annotations


# Constants documented in docs/ASSUMPTIONS.md (team assumptions, unvalidated)
LINE_ECONOMICS_ASSUMPTIONS: dict[str, dict[str, int]] = {
    "PCB": {
        "unit_cost_inr": 2850,
        "batch_exposure_units": 6,
        "hourly_downtime_inr": 42000,
    },
    "CNC": {
        "unit_cost_inr": 6400,
        "batch_exposure_units": 3,
        "hourly_downtime_inr": 78000,
    },
    "WELD": {
        "unit_cost_inr": 9200,
        "batch_exposure_units": 2,
        "hourly_downtime_inr": 54000,
    },
}

DOWNTIME_PREVENTED_MINS_BY_SEVERITY: dict[str, int] = {
    "LOW": 10,
    "MEDIUM": 20,
    "HIGH": 30,
    "CRITICAL": 45,
}

_NOMINAL_DEFECT_TYPES = {"NO_DEFECT_FOUND", "NOMINAL", "HEALTHY", "NONE", ""}


def calculate_avoidable_loss(
    line: str,
    defect_type: str,
    severity: str = "MEDIUM",
) -> dict[str, int]:
    """Return deterministic assumption-based avoidable loss (INR) and prevented downtime (mins)."""
    if (defect_type or "").upper() in _NOMINAL_DEFECT_TYPES:
        return {"avoidable_loss_inr": 0, "downtime_prevented_mins": 0}

    line_key = (line or "PCB").upper()
    if line_key.startswith("LINE_"):
        if "PCB" in line_key:
            line_key = "PCB"
        elif "CNC" in line_key:
            line_key = "CNC"
        elif "WELD" in line_key:
            line_key = "WELD"
        else:
            return {"avoidable_loss_inr": 0, "downtime_prevented_mins": 0}

    profile = LINE_ECONOMICS_ASSUMPTIONS.get(line_key)
    if profile is None:
        return {"avoidable_loss_inr": 0, "downtime_prevented_mins": 0}

    downtime_mins = DOWNTIME_PREVENTED_MINS_BY_SEVERITY.get((severity or "MEDIUM").upper(), 20)
    scrap_avoided = profile["unit_cost_inr"] * profile["batch_exposure_units"]
    downtime_avoided = int((profile["hourly_downtime_inr"] / 60.0) * downtime_mins)
    return {
        "avoidable_loss_inr": int(scrap_avoided + downtime_avoided),
        "downtime_prevented_mins": int(downtime_mins),
    }
