"""
backend/agents/validator_agent.py
SandboxSafetyValidatorAgent (Column 3 of Antigravity Verification Trace):
Executes deterministic mathematical checks against signed IATF 16949 control limits.
Emits pass/fail verification badges proving:
1. Operator feed dial % is strictly within signed PPAP window
2. Supervisor M01 Z-wear offset is within +-50.0 um ceiling
3. Tier-2 Programmed RPM is within motor stability window
4. Spindle chip-load torque ratio <= 1.15
"""
import json
import logging
from pathlib import Path
from typing import Optional
from backend.models.schemas import PPAPRemediationPlan, SandboxVerificationBadge
from backend.skills.ppap_sandbox_verifier import verify_ppap_window

logger = logging.getLogger("vinyas_ai.agents.validator")


class SandboxSafetyValidatorAgent:
    def __init__(self, control_limits_path: str = "config/ppap_control_limits.json"):
        self.control_limits = json.loads(Path(control_limits_path).read_text(encoding="utf-8"))

    def validate_plan(
        self,
        plan: PPAPRemediationPlan,
    ) -> tuple[bool, list[SandboxVerificationBadge]]:
        """
        Runs deterministic PPAP window math and returns (all_passed, badge_list).
        """
        all_passed, raw_badges = verify_ppap_window(plan, self.control_limits)
        typed_badges = [
            SandboxVerificationBadge(
                label=b["label"],
                passed=b["passed"],
                detail=b["detail"],
            )
            for b in raw_badges
        ]
        return all_passed, typed_badges
