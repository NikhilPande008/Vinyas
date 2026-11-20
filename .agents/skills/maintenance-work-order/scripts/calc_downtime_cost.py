#!/usr/bin/env python3
"""Deterministic Pune Tier-2/3 Automotive Scrap & Downtime Savings Calculator."""

from __future__ import annotations


LINE_ECONOMICS_INR = {
    "LINE_A_PCB": {
        "unit_cost_inr": 2850,
        "batch_exposure_units": 6,
        "hourly_downtime_inr": 42000,
        "default_downtime_saved_mins": 25,
    },
    "LINE_B_CNC": {
        "unit_cost_inr": 6400,
        "batch_exposure_units": 3,
        "hourly_downtime_inr": 78000,
        "default_downtime_saved_mins": 45,
    },
    "LINE_C_WELD": {
        "unit_cost_inr": 9200,
        "batch_exposure_units": 2,
        "hourly_downtime_inr": 54000,
        "default_downtime_saved_mins": 30,
    },
    "LINE_D_HEALTHY": {
        "unit_cost_inr": 0,
        "batch_exposure_units": 0,
        "hourly_downtime_inr": 0,
        "default_downtime_saved_mins": 0,
    },
}


def calculate_incident_savings(scenario_key: str) -> dict[str, int]:
    """Return deterministic scrap + downtime savings in INR and prevented minutes."""
    profile = LINE_ECONOMICS_INR.get(
        scenario_key,
        {
            "unit_cost_inr": 4000,
            "batch_exposure_units": 2,
            "hourly_downtime_inr": 48000,
            "default_downtime_saved_mins": 20,
        },
    )
    if scenario_key == "LINE_D_HEALTHY":
        return {"scrap_saved_inr": 0, "downtime_prevented_mins": 0}

    scrap_avoided = profile["unit_cost_inr"] * profile["batch_exposure_units"]
    downtime_mins = profile["default_downtime_saved_mins"]
    downtime_avoided = int((profile["hourly_downtime_inr"] / 60.0) * downtime_mins)
    return {
        "scrap_saved_inr": int(scrap_avoided + downtime_avoided),
        "downtime_prevented_mins": int(downtime_mins),
    }


if __name__ == "__main__":
    for key in LINE_ECONOMICS_INR:
        print(key, calculate_incident_savings(key))
