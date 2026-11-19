"""
backend/skills/roi_calculator.py
Economic ROI & Hardware Payback Calculator for Vinyas:
- Calculates cycle-time penalty vs. avoided casting (INR 14,000) & carbide insert (INR 2,200) scrap.
- Calculates validated 1.6-month (~48 days) net hardware payback math:
    * Upfront Clamp-On Hardware Kit: INR 35,000
    * Monthly Gross Value Saved: INR 34,500/mo (2 castings @ INR 14,000 + INR 6,500 insert life extension)
    * Monthly SaaS Fee: INR 12,500/mo
    * Net Monthly Plant Benefit: INR 22,000/mo
    * Net Hardware Payback: 35,000 / 22,000 = 1.6 months (~48 days)
"""
from typing import Any

HARDWARE_KIT_PRICE_INR = 35000
MONTHLY_SAAS_FEE_INR = 12500
MONTHLY_CASTINGS_SAVED_BASELINE = 2
MONTHLY_INSERT_LIFE_SAVINGS_INR = 6500


def calculate_hardware_payback(
    casting_cost_inr: int = 14000,
    hardware_kit_price_inr: int = HARDWARE_KIT_PRICE_INR,
    monthly_saas_fee_inr: int = MONTHLY_SAAS_FEE_INR,
    castings_saved_per_month: int = MONTHLY_CASTINGS_SAVED_BASELINE,
    insert_life_savings_per_month_inr: int = MONTHLY_INSERT_LIFE_SAVINGS_INR,
) -> dict[str, Any]:
    """Computes validated net hardware payback in months (~1.6) and days (~48)."""
    gross_monthly_savings = (casting_cost_inr * castings_saved_per_month) + insert_life_savings_per_month_inr
    net_monthly_benefit = max(gross_monthly_savings - monthly_saas_fee_inr, 1)
    payback_months = round(hardware_kit_price_inr / net_monthly_benefit, 1)
    payback_days = int(round((hardware_kit_price_inr / net_monthly_benefit) * 30.0))

    return {
        "hardware_kit_price_inr": hardware_kit_price_inr,
        "monthly_saas_fee_inr": monthly_saas_fee_inr,
        "gross_monthly_savings_inr": gross_monthly_savings,
        "net_monthly_benefit_inr": net_monthly_benefit,
        "hardware_payback_months": payback_months,
        "hardware_payback_days": payback_days,
        "payback_label": f"{payback_months:.1f} months (~{payback_days} days)",
    }


def calculate_remediation_roi(
    target_tool_id: str,
    operator_feedrate_dial_pct: int,
    control_limits: dict[str, Any],
    nominal_pass_time_sec: float = 28.0,
) -> dict[str, Any]:
    """
    Computes precise cycle-time penalty, direct per-event INR savings (INR 16,200),
    and validated 1.6-month (~48 days) net hardware payback metrics.
    """
    tools_map = control_limits.get("tools", control_limits)
    tool_limits = tools_map.get(target_tool_id, {})
    casting_cost = int(tool_limits.get("casting_cost_inr", 14000))
    insert_cost = int(tool_limits.get("insert_cost_inr", 2200))
    total_savings = casting_cost + insert_cost

    dial_ratio = max(operator_feedrate_dial_pct / 100.0, 0.50)
    adjusted_pass_time_sec = nominal_pass_time_sec / dial_ratio
    cycle_time_penalty_sec = round(max(0.0, adjusted_pass_time_sec - nominal_pass_time_sec), 1)

    payback = calculate_hardware_payback(casting_cost_inr=casting_cost)

    return {
        "cycle_time_penalty_sec": cycle_time_penalty_sec,
        "casting_savings_inr": casting_cost,
        "insert_savings_inr": insert_cost,
        "estimated_savings_inr": total_savings,
        "hardware_payback_months": payback["hardware_payback_months"],
        "hardware_payback_days": payback["hardware_payback_days"],
        "payback_label": payback["payback_label"],
        "net_monthly_benefit_inr": payback["net_monthly_benefit_inr"],
        "summary": (
            f"+INR {total_savings:,} Saved (INR {casting_cost:,} casting + "
            f"INR {insert_cost:,} insert) | +{cycle_time_penalty_sec}s cycle penalty | "
            f"Net Payback: {payback['payback_label']}"
        ),
    }
