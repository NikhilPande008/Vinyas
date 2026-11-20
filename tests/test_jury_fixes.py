"""Regression tests for the post-audit fixes (fast & offline, fake GenAI client)."""

from __future__ import annotations

import asyncio
import re
import threading
from types import SimpleNamespace

import pytest

from backend.config import DEFAULT_EVAL_TOKEN, PROJECT_ROOT, Settings
from backend.schemas import MatchedSOPRecord, SensorTelemetry
from backend.services.economics import ECONOMICS_NOT_ESTIMATED
from backend.services.metrics import compute_gate_token_accounting
from backend.services.model_router import GoogleModelRouter, build_t1b_prompt, parse_t1b_response


class _ScriptedClient:
    """Fake genai client: per-model delay (s) and either response text or an exception."""

    def __init__(self, script: dict[str, tuple[float, object]]) -> None:
        self.script = script
        self.calls: list[str] = []
        self._lock = threading.Lock()
        self.models = self

    def generate_content(self, model: str, contents, config=None):
        with self._lock:
            self.calls.append(model)
        delay, outcome = self.script.get(model, (0.0, RuntimeError("503 UNAVAILABLE")))
        import time

        time.sleep(delay)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome, usage_metadata=SimpleNamespace(prompt_token_count=100, candidates_token_count=20))


def _router(script, candidates, stagger=0.2, total=3.0) -> GoogleModelRouter:
    r = GoogleModelRouter(client=_ScriptedClient(script))
    r.settings = r.settings.model_copy(
        update={
            "tier1_visual_gate_model": candidates[0],
            "tier1_fallback_model": candidates[1] if len(candidates) > 1 else "",
            "tier1_second_fallback_model": candidates[2] if len(candidates) > 2 else "",
            "tier1_hedge_delay_sec": stagger,
            "tier1_total_timeout_sec": total,
        }
    )
    return r


_NOMINAL_JSON = '{"checks": {}, "observations": ["clean"], "vote": "NOMINAL", "confidence": 0.9, "bbox_hint": null}'
_ANOMALY_JSON = '{"checks": {}, "observations": ["blob joins leads"], "vote": "ANOMALY", "confidence": 0.8, "bbox_hint": [690, 540, 780, 610]}'


def _gate(router: GoogleModelRouter):
    return asyncio.run(
        router.run_tier1_visual_gate(
            line="PCB",
            line_meta={"machine_id": "M", "line_name": "L"},
            t1a_features={},
            t1a_flags=[],
            raw_image_bytes=b"\x89PNG fake",
        )
    )


def test_t1b_hedge_launches_backup_when_primary_is_slow_and_backup_wins():
    router = _router(
        {"slow-primary": (2.0, _NOMINAL_JSON), "fast-backup": (0.05, _ANOMALY_JSON)},
        ["slow-primary", "fast-backup"],
        stagger=0.2,
        total=3.0,
    )
    vote, _, obs, bbox, prov = _gate(router)
    assert vote == "ANOMALY"
    assert prov.model_id == "fast-backup"
    assert prov.producer == "FALLBACK_MODEL"
    statuses = {a.model_id: a.status for a in prov.attempts}
    assert statuses["fast-backup"] == "OK"
    assert statuses["slow-primary"] == "SKIPPED"
    assert bbox == [690, 540, 780, 610]


def test_t1b_all_models_fail_is_unavailable_fail_safe():
    router = _router({}, ["a", "b", "c"], stagger=0.1, total=2.0)
    vote, _, _, _, prov = _gate(router)
    assert vote == "UNAVAILABLE"
    assert prov.producer == "FALLBACK_RULES"
    assert [a.model_id for a in prov.attempts] == ["a", "b", "c"]


def test_t1b_prompt_has_no_labels_or_expected_answers():
    for line in ("PCB", "WELD", "CNC"):
        prompt = build_t1b_prompt(line, {"machine_id": "M", "line_name": "L"}, {"x": 1}, [])
        assert "MUST" not in prompt
        for label in ("SOLDER_BRIDGE", "INSUFFICIENT_SOLDER", "POROSITY_GAS_LOSS", "OUTER_RACE_FAULT", "NOMINAL\""):
            assert label not in prompt.split("Return strict JSON")[0]


def test_parse_t1b_rejects_bad_vote():
    with pytest.raises(ValueError):
        parse_t1b_response('{"vote": "MAYBE"}')


def test_rule_based_tier2_fallback_shows_no_money():
    router = GoogleModelRouter(client=_ScriptedClient({}))
    sop = MatchedSOPRecord(
        id="SOP-PCB-01",
        machine_type="SMT_REFLOW_PCB",
        fault_code="X",
        title="t",
        sop_markdown="1. step",
        torque_spec="n/a",
        similarity_score=0.5,
    )
    diag, prov = asyncio.run(
        router.run_tier2_multimodal_diagnosis(
            line="PCB",
            sensor_telemetry=SensorTelemetry(),
            dsp_features={},
            t1a_flags=["REFLOW_PEAK_OUT_OF_WINDOW"],
            raw_image_bytes=b"\x89PNG fake",
            envelope_png_bytes=None,
            matched_sops=[sop],
            active_skill={"name": "pcb-defect-triage", "skill_markdown": "", "references": {}},
            input_simulated=True,
            force_fallback=True,
        )
    )
    assert prov.producer == "FALLBACK_RULES"
    assert diag.estimated_avoidable_loss_inr == 0
    assert diag.estimated_downtime_prevented_mins == 0
    assert diag.economics_basis == ECONOMICS_NOT_ESTIMATED


def test_token_accounting_never_rewards_failed_tier2_calls():
    # 10 parts, all escalated, only 4 Tier-2 calls succeeded at 3,000 tokens each.
    acc = compute_gate_token_accounting(n_parts=10, t1_tokens_total=5_000, n_escalated=10, t2_success_tokens=[3000] * 4)
    assert acc["gated_tokens"] == 5_000 + 10 * 3_000
    assert acc["cloud_only_tokens"] == 30_000
    assert acc["saving_pct"] < 0  # escalating everything costs more than skipping the gate
    assert acc["t2_calls_failed"] == 6
    # 10 parts, 2 escalated -> real saving
    acc2 = compute_gate_token_accounting(n_parts=10, t1_tokens_total=5_000, n_escalated=2, t2_success_tokens=[3000, 3000])
    assert acc2["saving_pct"] == round(100 * (1 - (5_000 + 6_000) / 30_000), 1)


def test_eval_reveal_disabled_on_cloud_run_with_public_default_token(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "vinyas-ai")
    assert Settings(VINYAS_EVAL_TOKEN=DEFAULT_EVAL_TOKEN).eval_reveal_enabled is False
    assert Settings(VINYAS_EVAL_TOKEN="a-private-token").eval_reveal_enabled is True
    monkeypatch.delenv("K_SERVICE")
    assert Settings(VINYAS_EVAL_TOKEN=DEFAULT_EVAL_TOKEN).eval_reveal_enabled is True


def test_skill_bpfo_threshold_matches_dsp_code():
    code = (PROJECT_ROOT / "backend" / "dsp" / "envelope.py").read_text(encoding="utf-8")
    m = re.search(r"bpfo_snr_db >= ([\d.]+) and bpfo_2x_snr_db >= ([\d.]+)", code)
    assert m, "DSP threshold line not found"
    bpfo_db, harm_db = (int(float(x)) for x in m.groups())
    skill = (PROJECT_ROOT / ".agents/skills/bearing-acoustic-diagnostics/SKILL.md").read_text(encoding="utf-8")
    assert f"SNR >= {bpfo_db} dB" in skill and f"SNR >= {harm_db} dB" in skill
