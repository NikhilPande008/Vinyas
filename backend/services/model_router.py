"""Vinyas — Truthful Multi-Model Router (`backend/services/model_router.py`).

Implements:
- T1-B visual/context gate: `gemma-4-26b-a4b-it` -> `gemini-3.1-flash-lite` (fail-safe)
- T2 multimodal root-cause diagnosis: hedged request across primary & runner-up
  (chosen by `eval/model_selection.md`), strict Pydantic schema (no money fields),
  deterministic SOP guard (`sop_guard.py`), deterministic economics (`economics.py`)
- T4 hands-free co-pilot: `gemini-3.8-live` (15 s timeout, 24 kHz PCM -> WAV base64 + transcript)
  with truthful `gemini-3.1-flash-lite` text fallback and SOP guard
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import sys
import time
import uuid
import wave
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.schemas import (
    CopilotChatRequest,
    CopilotChatResponse,
    Evidence,
    MatchedSOPRecord,
    ModelAttempt,
    SensorTelemetry,
    StageProvenance,
    Tier2DiagnosisResult,
)
from backend.services.economics import calculate_avoidable_loss
from backend.services.metrics import ModelMetricsRegistry
from backend.services.sop_guard import (
    build_allowed_values_set,
    check_text_against_sop,
    guard_steps_against_sop,
)

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None  # type: ignore
    genai_types = None  # type: ignore


class Tier2ModelOutput(BaseModel):
    """Strict schema requested from the Tier-2 model (no money fields)."""

    defect_type: Literal[
        "SOLDER_BRIDGE",
        "INSUFFICIENT_SOLDER",
        "OUTER_RACE_FAULT",
        "IMBALANCE",
        "POROSITY_GAS_LOSS",
        "NO_DEFECT_FOUND",
        "OTHER",
    ]
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    root_cause_analysis: str
    evidence: list[Evidence] = Field(..., min_length=2)
    bbox: Optional[list[int]] = None
    matched_sop_id: str
    recommended_disposition: Literal["RELEASE", "HOLD", "REWORK", "SCRAP"]
    repair_steps: list[str] = Field(..., min_length=2, max_length=6)
    safety_precautions: list[str] = Field(..., min_length=2)


def _classify_exception(exc: Exception) -> tuple[Literal["TIMEOUT", "HTTP_429", "HTTP_503", "ERROR"], str]:
    msg = str(exc)
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "TIMEOUT", "request timed out"
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        return "HTTP_429", "429 RESOURCE_EXHAUSTED"
    if "503" in msg or "UNAVAILABLE" in msg:
        return "HTTP_503", "503 UNAVAILABLE"
    return "ERROR", f"{type(exc).__name__}: {msg[:140]}"


def _extract_tokens(response: Any) -> tuple[Optional[int], Optional[int]]:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None, None
    in_tok = getattr(usage, "prompt_token_count", None)
    out_tok = getattr(usage, "candidates_token_count", None)
    return (
        int(in_tok) if in_tok is not None else None,
        int(out_tok) if out_tok is not None else None,
    )


def _log_attempt_json(stage: str, attempt: ModelAttempt) -> None:
    record = {
        "event": "model_attempt",
        "stage": stage,
        "model_id": attempt.model_id,
        "status": attempt.status,
        "latency_ms": attempt.latency_ms,
        "input_tokens": attempt.input_tokens,
        "output_tokens": attempt.output_tokens,
        "error": attempt.error,
    }
    print(json.dumps(record, ensure_ascii=False), file=sys.stdout, flush=True)


def _pcm24k_to_wav_base64(pcm_bytes: bytes, sample_rate: int = 24000) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _strip_json_fences(raw: str) -> str:
    txt = raw.strip()
    if txt.startswith("```"):
        parts = txt.split("```")
        if len(parts) >= 2:
            txt = parts[1].strip()
            if txt.startswith("json"):
                txt = txt[4:].strip()
    return txt


class GoogleModelRouter:
    """Multi-model Google GenAI orchestrator with hedged routing, provenance, and metrics."""

    def __init__(self, client: Optional[Any] = None) -> None:
        self.settings = get_settings()
        self.metrics = ModelMetricsRegistry()
        self._client: Any = client
        if self._client is None and genai is not None and self.settings.gemini_api_key:
            try:
                self._client = genai.Client(api_key=self.settings.gemini_api_key)
            except Exception as exc:
                print(
                    json.dumps({"event": "genai_client_init_error", "error": type(exc).__name__}),
                    file=sys.stdout,
                    flush=True,
                )
                self._client = None

    def set_client(self, client: Any) -> None:
        self._client = client

    def get_routing_config(self) -> dict[str, Any]:
        return {
            "t1a_signal_gate": "deterministic DSP (NumPy/SciPy)",
            "t1b_visual_gate_primary": self.settings.tier1_visual_gate_model,
            "t1b_visual_gate_fallback": self.settings.tier1_fallback_model,
            "t2_diagnosis_primary": self.settings.tier2_primary_model,
            "t2_diagnosis_fallback": self.settings.tier2_fallback_model,
            "t2_hedge_delay_sec": self.settings.tier2_hedge_delay_sec,
            "t3_visual_overlay": "deterministic Pillow overlay from T2 model bbox",
            "t4_copilot_primary": self.settings.tier4_live_copilot_model,
            "t4_copilot_fallback": self.settings.tier4_fallback_model,
            "retrieval_embedding": self.settings.embedding_model,
            "wo_extraction": self.settings.wo_extract_model,
        }

    async def _call_single_model(
        self,
        stage: str,
        model_id: str,
        contents: Any,
        config: Optional[Any] = None,
        timeout_sec: float = 10.0,
        is_fallback: bool = False,
    ) -> tuple[Optional[Any], ModelAttempt]:
        t0 = time.perf_counter()
        if self._client is None:
            attempt = ModelAttempt(
                model_id=model_id,
                status="SKIPPED",
                latency_ms=0,
                error="GenAI client not configured",
            )
            _log_attempt_json(stage, attempt)
            return None, attempt

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self._client.models.generate_content,
                    model=model_id,
                    contents=contents,
                    config=config,
                ),
                timeout=timeout_sec,
            )
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            in_tok, out_tok = _extract_tokens(response)
            if response and getattr(response, "text", None):
                attempt = ModelAttempt(
                    model_id=model_id,
                    status="OK",
                    latency_ms=elapsed_ms,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                )
                self.metrics.record_attempt(model_id, "OK", elapsed_ms, is_fallback=is_fallback)
                _log_attempt_json(stage, attempt)
                return response, attempt
            attempt = ModelAttempt(
                model_id=model_id,
                status="ERROR",
                latency_ms=elapsed_ms,
                error="empty response text",
                input_tokens=in_tok,
                output_tokens=out_tok,
            )
            self.metrics.record_attempt(model_id, "ERROR", elapsed_ms, is_fallback=is_fallback)
            _log_attempt_json(stage, attempt)
            return None, attempt
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            status, err_msg = _classify_exception(exc)
            attempt = ModelAttempt(
                model_id=model_id,
                status=status,
                latency_ms=elapsed_ms,
                error=err_msg,
            )
            self.metrics.record_attempt(model_id, status, elapsed_ms, is_fallback=is_fallback)
            _log_attempt_json(stage, attempt)
            return None, attempt

    async def _call_genai_with_retry(
        self,
        stage: str,
        model_candidates: list[str],
        contents: Any,
        config: Optional[Any] = None,
        timeout_sec: float = 10.0,
    ) -> tuple[Optional[Any], Optional[str], list[ModelAttempt]]:
        attempts: list[ModelAttempt] = []
        for idx, model_id in enumerate(model_candidates):
            resp, attempt = await self._call_single_model(
                stage=stage,
                model_id=model_id,
                contents=contents,
                config=config,
                timeout_sec=timeout_sec,
                is_fallback=(idx > 0),
            )
            attempts.append(attempt)
            if resp is not None:
                return resp, model_id, attempts
        return None, None, attempts

    async def run_tier1_visual_gate(
        self,
        line: str,
        line_meta: dict[str, Any],
        t1a_features: dict[str, Any],
        t1a_flags: list[str],
        raw_image_bytes: bytes,
        input_simulated: bool = True,
        force_fallback: bool = False,
    ) -> tuple[
        Literal["NOMINAL", "ANOMALY", "UNAVAILABLE"],
        float,
        list[str],
        Optional[list[int]],
        StageProvenance,
    ]:
        """Tier-1B visual/context gate (`gemma-4-26b-a4b-it`, fallback `gemini-3.1-flash-lite`)."""
        t0 = time.perf_counter()
        attempts: list[ModelAttempt] = []

        if not force_fallback and self._client is not None and genai_types is not None:
            line_u = line.upper()
            if line_u == "CNC":
                domain_note = (
                    "Line type: CNC machined part surface. Note: the spindle bearing is internal and "
                    "not visible in this camera frame; judge only whether the machined surface looks "
                    "visually abnormal, and note any signal flags provided."
                )
            elif line_u == "PCB":
                domain_note = (
                    "Line type: Automotive SMT PCB (4-sided QFP IC). Look carefully for conductive solder "
                    "bridges spanning adjacent leads or starved/missing solder fillets on pads. "
                    "Translucent glossy glare off the leads on the green solder mask is cosmetic flux residue, not a bridge."
                )
            else:
                domain_note = (
                    "Line type: Robotic MIG steel weld seam. Look carefully for dark clustered porosity "
                    "pits/wormholes directly on the weld bead. Small droplets scattered on the plate "
                    "beside an otherwise clean bead are cosmetic spatter, not seam porosity."
                )

            prompt = (
                "You are a manufacturing quality visual gate. Inspect the image and numeric sensor features.\n"
                f"Machine: {line_meta.get('machine_id')} ({line_meta.get('line_name')})\n"
                f"{domain_note}\n"
                f"T1-A Signal Features: {json.dumps(t1a_features)}\n"
                f"T1-A Flags: {json.dumps(t1a_flags)}\n\n"
                "Return strict JSON only with keys:\n"
                '- "vote": "NOMINAL" or "ANOMALY"\n'
                '- "confidence": float 0.0 to 1.0\n'
                '- "observations": list of 1-3 short factual visual/feature observations\n'
                '- "bbox_hint": optional [ymin, xmin, ymax, xmax] integers 0-1000 around a visible defect, or null'
            )
            image_part = genai_types.Part.from_bytes(data=raw_image_bytes, mime_type="image/png")
            cfg = genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            )
            resp, used_model, attempts = await self._call_genai_with_retry(
                stage="T1B_GATE",
                model_candidates=[
                    self.settings.tier1_visual_gate_model,
                    self.settings.tier1_fallback_model,
                ],
                contents=[image_part, prompt],
                config=cfg,
                timeout_sec=5.0,
            )
            if resp and used_model and getattr(resp, "text", None):
                try:
                    parsed = json.loads(_strip_json_fences(resp.text))
                    vote_raw = str(parsed.get("vote", "")).upper()
                    if vote_raw not in ("NOMINAL", "ANOMALY"):
                        raise ValueError(f"Invalid vote: {vote_raw}")
                    conf = float(parsed.get("confidence", 0.7))
                    obs = [str(o) for o in (parsed.get("observations") or [])][:4]
                    bbox = parsed.get("bbox_hint")
                    if isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox):
                        bbox_clean: Optional[list[int]] = [max(0, min(1000, int(v))) for v in bbox]
                    else:
                        bbox_clean = None
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                    is_primary = used_model == self.settings.tier1_visual_gate_model
                    note = (
                        "Gemma 4 (cloud-served stand-in for an on-device Gemma edge model)"
                        if is_primary
                        else f"Fallback visual gate ({used_model})"
                    )
                    prov = StageProvenance(
                        stage="T1B_GATE",
                        producer="MODEL" if is_primary else "FALLBACK_MODEL",
                        model_id=used_model,
                        attempts=attempts,
                        latency_ms=elapsed_ms,
                        input_simulated=input_simulated,
                        note=note,
                    )
                    return (
                        "NOMINAL" if vote_raw == "NOMINAL" else "ANOMALY",
                        conf,
                        obs,
                        bbox_clean,
                        prov,
                    )
                except Exception:
                    if attempts:
                        attempts[-1].status = "SCHEMA_INVALID"

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        self.metrics.record_fallback_used("T1B_GATE")
        prov = StageProvenance(
            stage="T1B_GATE",
            producer="FALLBACK_RULES",
            model_id=None,
            attempts=attempts,
            latency_ms=elapsed_ms,
            input_simulated=input_simulated,
            note="gate unavailable -> human review (fail safe)",
        )
        return "UNAVAILABLE", 1.0, [], None, prov

    def _build_tier2_contents(
        self,
        line: str,
        sensor_telemetry: SensorTelemetry,
        dsp_features: dict[str, Any],
        t1a_flags: list[str],
        raw_image_bytes: bytes,
        envelope_png_bytes: Optional[bytes],
        matched_sops: list[MatchedSOPRecord],
        active_skill: dict[str, Any],
        language: str = "en-IN",
    ) -> list[Any]:
        sop_context = "\n".join(
            f"- [{s.id}] {s.title} (Fault: {s.fault_code}, Spec: {s.torque_spec}): {s.sop_markdown}"
            for s in matched_sops
        )
        skill_name = active_skill.get("name", "pcb-defect-triage")
        skill_md = active_skill.get("skill_markdown", "")
        refs_text = "\n".join(active_skill.get("references", {}).values())
        lang_hint = {
            "en-IN": "English",
            "hi-IN": "Hindi (Devanagari script, keeping SOP IDs and numeric units intact)",
            "mr-IN": "Marathi (Devanagari script, keeping SOP IDs and numeric units intact)",
        }.get(language, "English")

        prompt = (
            "You are Vinyas Tier-2 Multimodal Root-Cause Engine for discrete manufacturing.\n"
            f"Production Line: {line}\n"
            f"Output language for root_cause_analysis, repair_steps, safety_precautions: {lang_hint}\n"
            f"Sensor Telemetry: {sensor_telemetry.model_dump_json()}\n"
            f"Tier-1A DSP Features: {json.dumps(dsp_features)}\n"
            f"Tier-1A Flags: {json.dumps(t1a_flags)}\n"
            f"Active Domain Skill ({skill_name}):\n{skill_md}\n"
            f"Skill Reference Notes:\n{refs_text}\n"
            f"Retrieved SOPs (choose matched_sop_id strictly from these IDs):\n{sop_context}\n\n"
            "Instructions:\n"
            "- Classify defect_type strictly from: SOLDER_BRIDGE, INSUFFICIENT_SOLDER, OUTER_RACE_FAULT, "
            "IMBALANCE, POROSITY_GAS_LOSS, NO_DEFECT_FOUND, OTHER.\n"
            "- On CNC, the bearing is internal; use the DSP features and envelope spectrum PNG (not the part image) to diagnose OUTER_RACE_FAULT or IMBALANCE, and set bbox to null.\n"
            "- On PCB or WELD, if a visible defect exists, provide bbox as [ymin, xmin, ymax, xmax] integers 0..1000. If NO_DEFECT_FOUND, set bbox to null and recommended_disposition to RELEASE.\n"
            "- Only cite numeric parameters (torques, temperatures, ramp rates, gas flow, tolerances) that appear in the retrieved SOPs or skill references.\n"
            "- Provide at least 2 concrete evidence items citing their source."
        )
        parts: list[Any] = [genai_types.Part.from_bytes(data=raw_image_bytes, mime_type="image/png")]
        if envelope_png_bytes:
            parts.append(genai_types.Part.from_bytes(data=envelope_png_bytes, mime_type="image/png"))
        parts.append(prompt)
        return parts

    async def _run_hedged_tier2(
        self,
        contents: list[Any],
        config: Any,
        primary_model: str,
        runner_up_model: str,
        hedge_delay_sec: float,
        timeout_sec: float = 12.0,
    ) -> tuple[Optional[Tier2ModelOutput], Optional[str], list[ModelAttempt]]:
        """Hedged Tier-2 request: start primary, launch runner-up after hedge_delay_sec if still running."""
        attempts: list[ModelAttempt] = []

        async def _try_model(model_id: str, is_fb: bool) -> tuple[Optional[Tier2ModelOutput], str, ModelAttempt]:
            resp, att = await self._call_single_model(
                stage="T2_DIAGNOSIS",
                model_id=model_id,
                contents=contents,
                config=config,
                timeout_sec=timeout_sec,
                is_fallback=is_fb,
            )
            if resp is not None and getattr(resp, "text", None):
                try:
                    parsed = Tier2ModelOutput.model_validate_json(_strip_json_fences(resp.text))
                    return parsed, model_id, att
                except Exception as exc:
                    att.status = "SCHEMA_INVALID"
                    att.error = f"schema validation failed: {str(exc)[:100]}"
            return None, model_id, att

        primary_task = asyncio.create_task(_try_model(primary_model, False))
        done, _ = await asyncio.wait({primary_task}, timeout=min(hedge_delay_sec, 6.0))

        if primary_task in done:
            parsed, mid, att = primary_task.result()
            attempts.append(att)
            if parsed is not None:
                return parsed, mid, attempts
            # Primary failed or invalid schema -> immediately try runner-up
            if runner_up_model and runner_up_model != primary_model:
                parsed2, mid2, att2 = await _try_model(runner_up_model, True)
                attempts.append(att2)
                if parsed2 is not None:
                    return parsed2, mid2, attempts
            return None, None, attempts

        # Primary still running past hedge delay -> launch runner-up in parallel
        if not runner_up_model or runner_up_model == primary_model:
            parsed, mid, att = await primary_task
            attempts.append(att)
            return parsed, mid, attempts

        hedge_task = asyncio.create_task(_try_model(runner_up_model, True))
        pending: set[asyncio.Task[Any]] = {primary_task, hedge_task}
        winner: Optional[tuple[Tier2ModelOutput, str]] = None

        while pending:
            finished, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for t in finished:
                parsed, mid, att = t.result()
                attempts.append(att)
                if parsed is not None and winner is None:
                    winner = (parsed, mid)
                    for p in pending:
                        p.cancel()
                    pending.clear()
                    break

        if winner is not None:
            return winner[0], winner[1], attempts
        return None, None, attempts

    async def run_tier2_multimodal_diagnosis(
        self,
        line: str,
        sensor_telemetry: SensorTelemetry,
        dsp_features: dict[str, Any],
        t1a_flags: list[str],
        raw_image_bytes: bytes,
        envelope_png_bytes: Optional[bytes],
        matched_sops: list[MatchedSOPRecord],
        active_skill: dict[str, Any],
        language: str = "en-IN",
        input_simulated: bool = True,
        force_fallback: bool = False,
    ) -> tuple[Tier2DiagnosisResult, StageProvenance]:
        """Tier-2 Multimodal Root-Cause diagnosis with hedging, SOP guard, and deterministic economics."""
        t0 = time.perf_counter()
        incident_id = f"INC-{line.upper()}-{uuid.uuid4().hex[:5].upper()}"
        skill_name = active_skill.get("name", "pcb-defect-triage")
        valid_sop_ids = {s.id for s in matched_sops}
        sop_by_id = {s.id: s for s in matched_sops}
        attempts: list[ModelAttempt] = []

        if not force_fallback and self._client is not None and genai_types is not None:
            contents = self._build_tier2_contents(
                line=line,
                sensor_telemetry=sensor_telemetry,
                dsp_features=dsp_features,
                t1a_flags=t1a_flags,
                raw_image_bytes=raw_image_bytes,
                envelope_png_bytes=envelope_png_bytes,
                matched_sops=matched_sops,
                active_skill=active_skill,
                language=language,
            )
            cfg = genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=Tier2ModelOutput,
                temperature=0.15,
            )
            parsed, used_model, attempts = await self._run_hedged_tier2(
                contents=contents,
                config=cfg,
                primary_model=self.settings.tier2_primary_model,
                runner_up_model=self.settings.tier2_fallback_model,
                hedge_delay_sec=self.settings.tier2_hedge_delay_sec,
                timeout_sec=12.0,
            )
            if parsed is not None and used_model is not None:
                matched_sop_id = (
                    parsed.matched_sop_id
                    if parsed.matched_sop_id in valid_sop_ids
                    else (matched_sops[0].id if matched_sops else "SOP-UNMATCHED")
                )
                recommended_disp = parsed.recommended_disposition
                bbox = parsed.bbox
                if parsed.defect_type == "NO_DEFECT_FOUND":
                    recommended_disp = "RELEASE"
                    bbox = None
                elif line.upper() == "CNC":
                    bbox = None

                # Deterministic SOP numeric parameter guard
                ref_texts = [
                    active_skill.get("skill_markdown", ""),
                    *active_skill.get("references", {}).values(),
                ]
                chosen_sop = sop_by_id.get(matched_sop_id)
                if chosen_sop:
                    ref_texts.extend([chosen_sop.sop_markdown, chosen_sop.torque_spec, chosen_sop.title])
                for s in matched_sops:
                    ref_texts.extend([s.sop_markdown, s.torque_spec])

                repair_checked, unv_r = guard_steps_against_sop(parsed.repair_steps, ref_texts)
                safety_checked, unv_s = guard_steps_against_sop(parsed.safety_precautions, ref_texts)

                # Deterministic assumption-based economics
                econ = calculate_avoidable_loss(
                    line=line,
                    defect_type=parsed.defect_type,
                    severity=parsed.severity,
                )

                diagnosis = Tier2DiagnosisResult(
                    incident_id=incident_id,
                    defect_type=parsed.defect_type,
                    defect_class=parsed.defect_type.replace("_", " ").title(),
                    severity=parsed.severity,
                    confidence=parsed.confidence,
                    root_cause_analysis=parsed.root_cause_analysis,
                    evidence=parsed.evidence,
                    bbox=bbox,
                    matched_sop_id=matched_sop_id,
                    skill_applied=skill_name,
                    recommended_disposition=recommended_disp,
                    repair_steps=parsed.repair_steps,
                    repair_steps_checked=repair_checked,
                    safety_precautions=parsed.safety_precautions,
                    safety_precautions_checked=safety_checked,
                    unverified_value_count=unv_r + unv_s,
                    estimated_avoidable_loss_inr=econ["avoidable_loss_inr"],
                    estimated_downtime_prevented_mins=econ["downtime_prevented_mins"],
                )
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                is_primary = used_model == self.settings.tier2_primary_model
                prov = StageProvenance(
                    stage="T2_DIAGNOSIS",
                    producer="MODEL" if is_primary else "FALLBACK_MODEL",
                    model_id=used_model,
                    attempts=attempts,
                    latency_ms=elapsed_ms,
                    input_simulated=input_simulated,
                    note="Hedged primary/runner-up routing",
                )
                return diagnosis, prov

        # Deterministic rule-based fallback when AI is unavailable
        self.metrics.record_fallback_used("T2_DIAGNOSIS")
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        sop_id = matched_sops[0].id if matched_sops else "SOP-UNMATCHED"
        defect_type = "OTHER"
        if "BEARING_PERIODIC_IMPACT" in t1a_flags:
            defect_type = "OUTER_RACE_FAULT"
        elif "VIBRATION_ZONE_C_OR_D" in t1a_flags:
            defect_type = "IMBALANCE"
        elif "SHIELDING_GAS_LOW" in t1a_flags:
            defect_type = "POROSITY_GAS_LOSS"
        elif any(f.startswith("REFLOW_") for f in t1a_flags):
            defect_type = "SOLDER_BRIDGE"

        econ = calculate_avoidable_loss(line=line, defect_type=defect_type, severity="MEDIUM")
        steps = [
            "Quarantine part and notify shift Quality Engineer.",
            f"Follow retrieved SOP {sop_id} before adjusting machine parameters.",
        ]
        safety = [
            "Follow machine LOTO / ESD procedure before physical inspection.",
            "Do not resume production until QE records a disposition.",
        ]
        diagnosis = Tier2DiagnosisResult(
            incident_id=incident_id,
            defect_type=defect_type,
            defect_class=f"{defect_type.replace('_', ' ').title()} (rule-based fallback)",
            severity="MEDIUM",
            confidence=0.0,
            root_cause_analysis=(
                f"Tier-2 AI model was unavailable. Escalated flags: {t1a_flags or ['visual gate']}. "
                f"Hold part for QE review against {sop_id}."
            ),
            evidence=[
                Evidence(source="dsp_features", observation=f"T1-A flags: {t1a_flags or ['none']}"),
                Evidence(source="sop", observation=f"Top retrieved SOP: {sop_id}"),
            ],
            bbox=None,
            matched_sop_id=sop_id,
            skill_applied=skill_name,
            recommended_disposition="HOLD",
            repair_steps=steps,
            repair_steps_checked=[{"text": s, "unverified": False, "unverified_values": []} for s in steps],
            safety_precautions=safety,
            safety_precautions_checked=[{"text": s, "unverified": False, "unverified_values": []} for s in safety],
            unverified_value_count=0,
            estimated_avoidable_loss_inr=econ["avoidable_loss_inr"],
            estimated_downtime_prevented_mins=econ["downtime_prevented_mins"],
        )
        prov = StageProvenance(
            stage="T2_DIAGNOSIS",
            producer="FALLBACK_RULES",
            model_id=None,
            attempts=attempts,
            latency_ms=elapsed_ms,
            input_simulated=input_simulated,
            note="RULE-BASED (AI unavailable)",
        )
        return diagnosis, prov

    async def run_tier4_live_copilot(
        self,
        request: CopilotChatRequest,
        matched_sop: MatchedSOPRecord,
        force_fallback: bool = False,
    ) -> CopilotChatResponse:
        """Tier-4 Co-Pilot using `gemini-3.8-live` (15 s timeout, audio + transcript) with text fallback."""
        t0 = time.perf_counter()
        attempts: list[ModelAttempt] = []
        lang_name = {"en-IN": "English", "hi-IN": "Hindi", "mr-IN": "Marathi"}.get(request.language, "English")
        prompt = (
            f"Answer in {lang_name}, max 3 short sentences, cite SOP {matched_sop.id}, "
            "and ONLY use numeric values that appear in the SOP below.\n"
            f"SOP [{matched_sop.id}] ({matched_sop.title}): {matched_sop.sop_markdown}\n"
            f"Spec: {matched_sop.torque_spec}\n"
            f"Question: {request.question}"
        )
        allowed_vals = build_allowed_values_set([matched_sop.sop_markdown, matched_sop.torque_spec, matched_sop.title])

        if not force_fallback and self._client is not None and genai_types is not None:
            t_live = time.perf_counter()
            live_err_note = ""
            try:
                live_cfg = genai_types.LiveConnectConfig(
                    response_modalities=["AUDIO"],
                    output_audio_transcription=genai_types.AudioTranscriptionConfig(),
                )
                async with asyncio.timeout(15.0):
                    async with self._client.aio.live.connect(
                        model=self.settings.tier4_live_copilot_model,
                        config=live_cfg,
                    ) as session:
                        await session.send_client_content(
                            turns=genai_types.Content(
                                role="user",
                                parts=[genai_types.Part.from_text(text=prompt)],
                            )
                        )
                        transcript_chunks: list[str] = []
                        pcm_chunks: list[bytes] = []
                        async for msg in session.receive():
                            sc = getattr(msg, "server_content", None)
                            if (
                                sc
                                and getattr(sc, "output_transcription", None)
                                and sc.output_transcription.text
                            ):
                                transcript_chunks.append(sc.output_transcription.text)
                            if sc and getattr(sc, "model_turn", None) and sc.model_turn.parts:
                                for part in sc.model_turn.parts:
                                    inline = getattr(part, "inline_data", None)
                                    if inline and getattr(inline, "data", None):
                                        pcm_chunks.append(inline.data)
                            if sc and getattr(sc, "turn_complete", False):
                                break
                        live_text = "".join(transcript_chunks).strip()
                        live_ms = int((time.perf_counter() - t_live) * 1000)
                        if live_text:
                            audio_b64 = _pcm24k_to_wav_base64(b"".join(pcm_chunks)) if pcm_chunks else None
                            att = ModelAttempt(
                                model_id=self.settings.tier4_live_copilot_model,
                                status="OK",
                                latency_ms=live_ms,
                            )
                            attempts.append(att)
                            self.metrics.record_attempt(self.settings.tier4_live_copilot_model, "OK", live_ms)
                            _log_attempt_json("T4_COPILOT", att)
                            elapsed_ms = int((time.perf_counter() - t0) * 1000)
                            unverified = check_text_against_sop(live_text, allowed_vals)
                            prov = StageProvenance(
                                stage="T4_COPILOT",
                                producer="MODEL",
                                model_id=self.settings.tier4_live_copilot_model,
                                attempts=attempts,
                                latency_ms=elapsed_ms,
                                input_simulated=False,
                                note="Gemini Live audio + transcript",
                            )
                            return CopilotChatResponse(
                                answer=live_text,
                                audio_wav_base64=audio_b64,
                                model_used=self.settings.tier4_live_copilot_model,
                                producer="MODEL",
                                grounded_sop_id=matched_sop.id,
                                latency_ms=elapsed_ms,
                                unverified_values=unverified,
                                provenance=prov,
                            )
                        live_err_note = "empty transcript"
            except Exception as exc:
                live_ms = int((time.perf_counter() - t_live) * 1000)
                status, err_msg = _classify_exception(exc)
                live_err_note = err_msg
                att = ModelAttempt(
                    model_id=self.settings.tier4_live_copilot_model,
                    status=status,
                    latency_ms=live_ms,
                    error=err_msg,
                )
                attempts.append(att)
                self.metrics.record_attempt(self.settings.tier4_live_copilot_model, status, live_ms)
                _log_attempt_json("T4_COPILOT", att)

            # Text fallback
            resp, used_model, fb_attempts = await self._call_genai_with_retry(
                stage="T4_COPILOT",
                model_candidates=[self.settings.tier4_fallback_model],
                contents=prompt,
                timeout_sec=8.0,
            )
            attempts.extend(fb_attempts)
            if resp and used_model and getattr(resp, "text", None):
                ans = resp.text.strip()
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                unverified = check_text_against_sop(ans, allowed_vals)
                prov = StageProvenance(
                    stage="T4_COPILOT",
                    producer="FALLBACK_MODEL",
                    model_id=used_model,
                    attempts=attempts,
                    latency_ms=elapsed_ms,
                    input_simulated=False,
                    note=f"TEXT FALLBACK (Live unavailable: {live_err_note})",
                )
                return CopilotChatResponse(
                    answer=ans,
                    audio_wav_base64=None,
                    model_used=used_model,
                    producer="FALLBACK_MODEL",
                    grounded_sop_id=matched_sop.id,
                    latency_ms=elapsed_ms,
                    unverified_values=unverified,
                    provenance=prov,
                )

        self.metrics.record_fallback_used("T4_COPILOT")
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        fallback_answer = f"[{matched_sop.id}] {matched_sop.sop_markdown} Spec: {matched_sop.torque_spec}."
        prov = StageProvenance(
            stage="T4_COPILOT",
            producer="FALLBACK_RULES",
            model_id=None,
            attempts=attempts,
            latency_ms=elapsed_ms,
            input_simulated=False,
            note="RULE-BASED SOP excerpt (AI unavailable)",
        )
        return CopilotChatResponse(
            answer=fallback_answer,
            audio_wav_base64=None,
            model_used=None,
            producer="FALLBACK_RULES",
            grounded_sop_id=matched_sop.id,
            latency_ms=elapsed_ms,
            unverified_values=[],
            provenance=prov,
        )
