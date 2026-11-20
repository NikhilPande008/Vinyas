"""Deterministic SOP numeric parameter guard (`backend/services/sop_guard.py`).

Extracts every number+unit from AI-generated repair steps, safety precautions,
and co-pilot answers, and flags any value not present in the matched SOP text,
torque spec, or active skill references.
"""

from __future__ import annotations

import re
from typing import Iterable

from backend.schemas import RepairStepChecked


# Matches numbers (including ranges/decimals/signs) followed by manufacturing units
_VALUE_UNIT_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"([+-]?\d+(?:\.\d+)?)"
    r"\s*"
    r"(°C/s|°C/sec|C/s|°C|Nm|N·m|mm/s|mm|µm|um|L/min|MPa|bar|rpm|RPM|%|kHz|Hz|s\b|sec\b|V\b)",
    flags=re.IGNORECASE,
)


def _normalize_token(num_str: str, unit_str: str) -> str:
    try:
        val = float(num_str)
        num_norm = str(int(val)) if val.is_integer() else f"{val:g}"
    except ValueError:
        num_norm = num_str.strip()

    u = unit_str.strip().lower()
    unit_map = {
        "°c/sec": "°c/s",
        "c/s": "°c/s",
        "n·m": "nm",
        "um": "µm",
        "sec": "s",
    }
    u = unit_map.get(u, u)
    return f"{num_norm} {u}"


def extract_numeric_unit_values(text: str) -> list[tuple[str, str]]:
    """Return list of (original_match_str, normalized_key) for all number+unit pairs."""
    found: list[tuple[str, str]] = []
    for m in _VALUE_UNIT_RE.finditer(text or ""):
        orig = m.group(0).strip()
        norm = _normalize_token(m.group(1), m.group(2))
        found.append((orig, norm))
    return found


def build_allowed_values_set(reference_texts: Iterable[str]) -> set[str]:
    """Build normalized set of all numeric+unit values present in authoritative SOP/skill docs."""
    allowed: set[str] = set()
    for txt in reference_texts:
        for _, norm in extract_numeric_unit_values(txt):
            allowed.add(norm)
    return allowed


def check_text_against_sop(text: str, allowed_values: set[str]) -> list[str]:
    """Return list of original number+unit strings in `text` not found in `allowed_values`."""
    unverified: list[str] = []
    for orig, norm in extract_numeric_unit_values(text):
        if norm not in allowed_values and orig not in unverified:
            unverified.append(orig)
    return unverified


def guard_steps_against_sop(
    steps: list[str],
    reference_texts: Iterable[str],
) -> tuple[list[RepairStepChecked], int]:
    """Check each step against SOP/skill references; return checked steps and total unverified count."""
    allowed = build_allowed_values_set(reference_texts)
    checked: list[RepairStepChecked] = []
    total_unverified = 0
    for step in steps:
        bad = check_text_against_sop(step, allowed)
        total_unverified += len(bad)
        checked.append(
            RepairStepChecked(
                text=step,
                unverified=len(bad) > 0,
                unverified_values=bad,
            )
        )
    return checked, total_unverified
