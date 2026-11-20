"""Fail-safe Tier-1 decision combiner (`backend/services/gate.py`).

Rule:
  - When T1-B is SKIPPED (e.g. CNC, where the bearing is internal and not visible):
    T1-A deterministic DSP decides (HEALTHY if no escalating flags, else ESCALATE).
  - Otherwise:
    HEALTHY only if T1-A has no escalating flags AND T1-B succeeded with vote == "NOMINAL".
    Any escalating T1-A flag, T1-B ANOMALY vote, or T1-B failure -> ESCALATE.
"""

from __future__ import annotations

from typing import Literal, Optional

from backend.dsp.envelope import T1AResult
from backend.schemas import StageProvenance, Tier1TriageResult


def make_skipped_t1b_provenance(
    input_simulated: bool,
    note: str = "bearing not visible; vibration-led",
) -> StageProvenance:
    """Return a truthful SKIPPED provenance entry when T1-B is intentionally bypassed."""
    return StageProvenance(
        stage="T1B_GATE",
        producer="SKIPPED",
        model_id=None,
        attempts=[],
        latency_ms=0,
        input_simulated=input_simulated,
        note=note,
    )


def combine_tier1_votes(
    t1a: T1AResult,
    t1b_vote: Optional[Literal["NOMINAL", "ANOMALY", "UNAVAILABLE", "SKIPPED"]],
    t1b_confidence: float,
    t1b_observations: list[str],
    t1b_bbox_hint: Optional[list[int]],
    t1b_provenance: StageProvenance,
    input_simulated: bool,
) -> Tier1TriageResult:
    """Combine deterministic T1-A and model T1-B votes under fail-safe quality logic."""
    prov_t1a = StageProvenance(
        stage="T1A_DSP",
        producer="DETERMINISTIC",
        model_id=None,
        attempts=[],
        latency_ms=t1a.latency_ms,
        input_simulated=input_simulated,
        note=t1a.summary,
    )

    t1b_skipped = t1b_vote == "SKIPPED"
    t1b_failed = t1b_vote is None or t1b_vote == "UNAVAILABLE"
    reasons: list[str] = []

    if t1a.any_escalating_flag:
        reasons.append(f"Signal gate flagged: {', '.join(t1a.escalating_flags)}")
    if t1b_vote == "ANOMALY":
        obs_str = "; ".join(t1b_observations[:2]) if t1b_observations else "visual anomaly detected"
        reasons.append(f"Visual gate flagged anomaly: {obs_str}")
    if t1b_failed:
        reasons.append("Visual gate unavailable -> fail-safe escalation for human review")

    if reasons:
        pass_status: Literal["HEALTHY", "ESCALATE"] = "ESCALATE"
        reason_text = " | ".join(reasons)
        conf = max(t1b_confidence, 0.85 if t1a.any_escalating_flag else t1b_confidence)
    else:
        pass_status = "HEALTHY"
        info_note = f" (info: {', '.join(t1a.info_flags)})" if t1a.info_flags else ""
        if t1b_skipped:
            skip_note = t1b_provenance.note or "bearing not visible; vibration-led"
            reason_text = f"Signal gate nominal{info_note}; visual gate skipped ({skip_note})."
        else:
            reason_text = f"Signal gate nominal{info_note} and visual gate voted NOMINAL."
        conf = t1b_confidence

    total_t1_ms = t1a.latency_ms + t1b_provenance.latency_ms
    executed_model = t1b_provenance.model_id or ("DETERMINISTIC_DSP" if t1b_skipped else t1b_provenance.producer)

    return Tier1TriageResult(
        pass_status=pass_status,
        anomaly_confidence=round(min(1.0, max(0.0, conf)), 3),
        edge_latency_ms=total_t1_ms,
        escalation_reason=reason_text,
        executed_model=executed_model,
        short_circuited=(pass_status == "HEALTHY"),
        t1a_flags=t1a.all_flags,
        t1a_summary=t1a.summary,
        t1b_vote=t1b_vote or "UNAVAILABLE",
        t1b_observations=t1b_observations,
        t1b_bbox_hint=t1b_bbox_hint,
        provenance_t1a=prov_t1a,
        provenance_t1b=t1b_provenance,
    )
