"""
backend/skills/ppap_sandbox_verifier.py
Deterministic IATF 16949 PPAP Sandbox Verifier:
Evaluates PPAPRemediationPlan against signed control limits (config/ppap_control_limits.json).
Emits structured mathematical badges for Column 3 of the Antigravity Supervisor Cockpit:
1. Day-1 Feedrate Override Dial Window Check
2. Day-1 M01 Z-Wear Offset Ceiling Check (+-50.0 um)
3. Tier-2 Programmed RPM Window Check
4. Spindle Chip-Load Torque Ratio Check (<= 1.15)
"""
from typing import Any
from backend.models.schemas import PPAPRemediationPlan, SandboxVerificationBadge


def verify_ppap_window(
    plan: PPAPRemediationPlan,
    control_limits: dict[str, Any],
) -> tuple[bool, list[dict[str, Any]]]:
    """
    Deterministic IATF 16949 & torque verifier for V2.1 nested schema.
    Returns (all_passed, badge_list) for the 3-Column Antigravity Verification Trace.
    """
    badges: list[dict[str, Any]] = []
    tool_limits = control_limits.get(plan.target_tool_id)
    if not tool_limits:
        return False, [
            {
                "label": "Tool ID Check",
                "passed": False,
                "detail": f"Unknown tool identifier '{plan.target_tool_id}'",
            }
        ]

    dial_pct = plan.day1_manual_action.operator_feedrate_dial_pct
    wear_um = plan.day1_manual_action.m01_manual_wear_offset_z_microns
    sim_rpm = plan.tier2_focas_simulation.programmed_rpm_override

    # 1. Day-1 Feedrate Override Dial check
    min_feed = tool_limits["min_feed_pct"]
    max_feed = tool_limits["max_feed_pct"]
    feed_ok = min_feed <= dial_pct <= max_feed
    badges.append(
        {
            "label": "Day-1 Feed Override Dial",
            "passed": feed_ok,
            "detail": f"{dial_pct}% in [{min_feed}..{max_feed}%]",
        }
    )

    # 2. Day-1 M01 Z-Wear Offset check
    max_wear = tool_limits["max_wear_offset_microns"]
    offset_ok = abs(wear_um) <= max_wear
    badges.append(
        {
            "label": "M01 Z-Wear Offset Ceiling",
            "passed": offset_ok,
            "detail": f"{wear_um:+.1f} um within +-{max_wear:.1f} um",
        }
    )

    # 3. Tier-2 RPM Window check
    min_rpm = tool_limits["min_rpm"]
    max_rpm = tool_limits["max_rpm"]
    rpm_ok = min_rpm <= sim_rpm <= max_rpm
    badges.append(
        {
            "label": "Tier-2 RPM Window",
            "passed": rpm_ok,
            "detail": f"{sim_rpm} RPM in [{min_rpm}..{max_rpm}]",
        }
    )

    # 4. Spindle Chip-Load Torque Ratio check
    nominal_rpm = tool_limits.get("nominal_rpm", 3800)
    chip_load_ratio = (dial_pct / 100.0) / (sim_rpm / nominal_rpm)
    max_torque_ratio = tool_limits.get("max_chip_load_ratio", 1.15)
    torque_ok = chip_load_ratio <= max_torque_ratio
    badges.append(
        {
            "label": "Spindle Chip-Load Torque",
            "passed": torque_ok,
            "detail": f"Ratio {chip_load_ratio:.2f} <= {max_torque_ratio:.2f}",
        }
    )

    all_passed = all(b["passed"] for b in badges)
    return all_passed, badges
