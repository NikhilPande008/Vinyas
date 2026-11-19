"""
backend/skills/control_plan_solver.py
Deterministic Physics Control-Plan Solver ("Physics Calculates, AI Diagnoses"):
Takes detected chatter frequency (Hz), spindle RPM, flute count Z, and signed
`config/control_plan_limits.json` to compute and clamp:
  - operator_feedrate_dial_pct in [70, 110]%
  - spindle_speed_dial_pct in [80, 115]%
  - relative_chip_load_ratio in [0.65, 1.15]
Emits a validated `DeterministicControlSolution` with structured [PASS] badges.
"""
import json
from pathlib import Path
from typing import Any, Literal, Optional
from backend.models.schemas import DeterministicControlSolution, SandboxVerificationBadge

DEFAULT_CONTROL_PLAN_PATH = Path("config/control_plan_limits.json")


def load_control_plan_limits(path: Optional[Path] = None) -> dict[str, Any]:
    target = path or DEFAULT_CONTROL_PLAN_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def solve_deterministic_control_plan(
    detected_chatter_hz: float,
    spindle_rpm: int,
    flute_count_z: int,
    target_tool_id: Literal["T01", "T02", "T03", "T04"] = "T03",
    control_plan_limits: Optional[dict[str, Any]] = None,
    requested_wear_offset_z_microns: float = 12.0,
) -> DeterministicControlSolution:
    """
    Computes stable regenerative chatter detuning overrides strictly clamped to
    the signed Part Control Plan limits:
      - Feedrate Override Dial: [70, 110]%
      - Spindle Speed Override Dial: [80, 115]%
      - Relative Chip-Load Ratio = (feed_pct / speed_pct) in [0.65, 1.15]
    """
    limits_doc = control_plan_limits or load_control_plan_limits()
    tools_map = limits_doc.get("tools", limits_doc)
    tool_cfg = tools_map.get(target_tool_id, tools_map["T03"])

    min_feed = int(tool_cfg.get("min_feed_pct", 70))
    max_feed = int(tool_cfg.get("max_feed_pct", 110))
    min_speed = int(tool_cfg.get("min_spindle_speed_pct", 80))
    max_speed = int(tool_cfg.get("max_spindle_speed_pct", 115))
    min_chip = float(tool_cfg.get("min_chip_load_ratio", 0.65))
    max_chip = float(tool_cfg.get("max_chip_load_ratio", 1.15))
    max_wear_um = float(tool_cfg.get("max_wear_offset_microns", 50.0))

    nominal_rpm = max(int(spindle_rpm or tool_cfg.get("nominal_rpm", 3800)), 500)
    z = max(int(flute_count_z or tool_cfg.get("flute_count_z", 2)), 1)

    # 1. Stability lobe speed detuning:
    # Tooth-passing frequency f_tooth = (N * Z) / 60.
    # Shift spindle speed away from resonant chatter harmonic into the adjacent stable lobe pocket.
    f_tooth = (nominal_rpm * z) / 60.0
    if detected_chatter_hz > 100.0 and f_tooth > 1.0:
        lobe_order = max(1.0, round(detected_chatter_hz / f_tooth))
        # Target half-integer lobe pocket slightly below nominal to lower thermal & cutting forces
        candidate_rpm = (60.0 * detected_chatter_hz) / (z * (lobe_order + 0.5))
        raw_speed_pct = int(round((candidate_rpm / nominal_rpm) * 100.0))
        # If candidate sits right on 100% (no detuning), apply a deterministic -10% lobe shift
        if abs(raw_speed_pct - 100) < 5:
            raw_speed_pct = 90
    else:
        raw_speed_pct = 90

    spindle_speed_dial_pct = max(min_speed, min(max_speed, raw_speed_pct))
    target_rpm = int(round(nominal_rpm * (spindle_speed_dial_pct / 100.0)))

    # 2. Stabilizing feedrate dial reduction (default 85% for flank-wear chatter)
    raw_feed_pct = 85 if detected_chatter_hz > 100.0 else 100
    operator_feedrate_dial_pct = max(min_feed, min(max_feed, raw_feed_pct))

    # 3. Clamp relative chip-load ratio = (feed_pct / 100) / (speed_pct / 100) strictly within [0.65, 1.15]
    chip_ratio = (operator_feedrate_dial_pct / 100.0) / (spindle_speed_dial_pct / 100.0)
    if chip_ratio > max_chip:
        clamped_feed = int(max_chip * spindle_speed_dial_pct)
        operator_feedrate_dial_pct = max(min_feed, min(max_feed, clamped_feed))
        chip_ratio = (operator_feedrate_dial_pct / 100.0) / (spindle_speed_dial_pct / 100.0)
    elif chip_ratio < min_chip:
        clamped_feed = int(round(min_chip * spindle_speed_dial_pct + 0.5))
        operator_feedrate_dial_pct = max(min_feed, min(max_feed, clamped_feed))
        chip_ratio = (operator_feedrate_dial_pct / 100.0) / (spindle_speed_dial_pct / 100.0)

    relative_chip_load_ratio = round(chip_ratio, 3)

    # 4. Clamp manual M01 Z-wear offset to signed ceiling
    clamped_wear_um = round(
        max(-max_wear_um, min(max_wear_um, float(requested_wear_offset_z_microns))),
        1,
    )

    # 5. Deterministic Verification Assertion Badges
    feed_ok = min_feed <= operator_feedrate_dial_pct <= max_feed
    speed_ok = min_speed <= spindle_speed_dial_pct <= max_speed
    chip_ok = min_chip <= relative_chip_load_ratio <= max_chip
    wear_ok = abs(clamped_wear_um) <= max_wear_um

    badges = [
        SandboxVerificationBadge(
            label="Feedrate Override Dial",
            passed=feed_ok,
            detail=f"{operator_feedrate_dial_pct}% in [{min_feed}..{max_feed}%]",
        ),
        SandboxVerificationBadge(
            label="Spindle Speed Override Dial",
            passed=speed_ok,
            detail=f"{spindle_speed_dial_pct}% ({target_rpm} RPM) in [{min_speed}..{max_speed}%]",
        ),
        SandboxVerificationBadge(
            label="Relative Chip-Load Ratio",
            passed=chip_ok,
            detail=f"Ratio {relative_chip_load_ratio:.2f} in [{min_chip:.2f}..{max_chip:.2f}]",
        ),
        SandboxVerificationBadge(
            label="M01 Z-Wear Offset Ceiling",
            passed=wear_ok,
            detail=f"{clamped_wear_um:+.1f} um within +-{max_wear_um:.1f} um",
        ),
    ]

    all_passed = all(b.passed for b in badges)

    return DeterministicControlSolution(
        target_tool_id=target_tool_id,
        operator_feedrate_dial_pct=operator_feedrate_dial_pct,
        spindle_speed_dial_pct=spindle_speed_dial_pct,
        nominal_rpm=nominal_rpm,
        target_rpm=target_rpm,
        flute_count_z=z,
        relative_chip_load_ratio=relative_chip_load_ratio,
        m01_manual_wear_offset_z_microns=clamped_wear_um,
        require_insert_indexing=detected_chatter_hz > 100.0,
        all_passed=all_passed,
        verification_badges=badges,
    )
