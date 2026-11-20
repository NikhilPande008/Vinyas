#!/usr/bin/env python3
"""Deterministic Pune Tier-2/3 Automotive Avoidable-Loss Calculator.

Thin wrapper delegating to `backend.services.economics` (single source of truth).
"""

from __future__ import annotations

from backend.services.economics import (
    LINE_ECONOMICS_ASSUMPTIONS,
    calculate_avoidable_loss,
)


def calculate_incident_savings(
    line: str,
    defect_type: str = "OTHER",
    severity: str = "HIGH",
) -> dict[str, int]:
    return calculate_avoidable_loss(line=line, defect_type=defect_type, severity=severity)


if __name__ == "__main__":
    for line_key in LINE_ECONOMICS_ASSUMPTIONS:
        print(line_key, calculate_avoidable_loss(line_key, "OTHER", "HIGH"))
