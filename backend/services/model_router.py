"""Vinyas — Truthful Multi-Model Router (`backend/services/model_router.py`).

Records exact per-attempt provenance (model ID, status, measured latency, token counts)
and logs every model attempt as a single JSON line to stdout.
No shared mutable inference mode, no latency padding, and no mislabelled fallbacks.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from typing import Any, Literal, Optional

from backend.config import get_settings
from backend.schemas import (
    CopilotChatRequest,
    CopilotChatResponse,
    MatchedSOPRecord,
    ModelAttempt,
    SensorTelemetry,
    StageProvenance,
    Tier1TriageResult,
    Tier2DiagnosisResult,
)
from backend.services.metrics import ModelMetricsRegistry

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None  # type: ignore
    genai_types = None  # type: ignore


def _classify_exception(exc: Exception) -> tuple[Literal["TIMEOUT", "HTTP_429", "HTTP_503", "ERROR"], str]:
    msg = str(exc)
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "TIMEOUT", "request timed out"
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        return "HTTP_429", "429 RESOURCE_EXHAUSTED"
    if "503" in msg or "UNAVAILABLE" in msg:
        return "HTTP_503", "503 UNAVAILABLE"
    short = f"{type(exc).__name__}: {msg[:140]}"
    return "ERROR", short


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


class GoogleModelRouter:
    """Multi-model Google GenAI orchestrator with truthful provenance and metrics."""

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
        """Allow dependency injection of a fake client for offline tests."""
        self._client = client

    def get_routing_config(self) -> dict[str, Any]:
        return {
            "t1a_signal_gate": "deterministic DSP (NumPy/SciPy)",
            "t1b_visual_gate_primary": self.settings.tier1_visual_gate_model,
            "t1b_visual_gate_fallback": self.settings.tier1_fallback_model,
            "t2_diagnosis_primary": self.settings.tier2_primary_model,
            "t2_diagnosis_fallback": self.settings.tier2_fallback_model,
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
        """Try candidate models in order, recording every attempt truthfully."""
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
        """Tier-1B visual/context gate (`gemma-4-26b-a4b-it`, fallback `gemini-3.1-flash-lite`).

        Never receives ground-truth labels or scenario verdicts. Fails safe on timeout/error.
        """
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
                    raw_txt = resp.text.strip()
                    if raw_txt.startswith("```"):
                        raw_txt = raw_txt.split("```")[1].lstrip("json").strip()
                    parsed = json.loads(raw_txt)
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

    async def run_tier2_multimodal_diagnosis(
        self,
        scenario_key: str,
        sensor_telemetry: SensorTelemetry,
        raw_image_bytes: bytes,
        matched_sops: list[MatchedSOPRecord],
        active_skill: dict[str, Any],
        input_simulated: bool = True,
        force_fallback: bool = False,
    ) -> tuple[Tier2DiagnosisResult, StageProvenance]:
        """Tier-2 Multimodal Root-Cause diagnosis with truthful provenance."""
        t0 = time.perf_counter()
        incident_id = f"INC-{uuid.uuid4().hex[:6].upper()}"
        top_sop = matched_sops[0] if matched_sops else None
        sop_context = "\n".join(
            f"- [{s.id}] {s.title} (Fault: {s.fault_code}, Torque: {s.torque_spec}): {s.sop_markdown}"
            for s in matched_sops
        )
        skill_name = active_skill.get("name", "pcb-defect-triage")
        skill_md = active_skill.get("skill_markdown", "")
        refs_text = "\n".join(active_skill.get("references", {}).values())
        attempts: list[ModelAttempt] = []

        if not force_fallback and self._client is not None and genai_types is not None:
            prompt = (
                "You are Vinyas Tier-2 Multimodal Root-Cause Engine for discrete manufacturing.\n"
                f"Incident ID: {incident_id}\n"
                f"Sensor Telemetry: {sensor_telemetry.model_dump_json()}\n"
                f"Active Skill ({skill_name}):\n{skill_md}\n"
                f"Skill References:\n{refs_text}\n"
                f"Retrieved SOPs:\n{sop_context}\n\n"
                "Return strict JSON matching the schema. Do not invent financial amounts."
            )
            image_part = genai_types.Part.from_bytes(data=raw_image_bytes, mime_type="image/png")
            cfg = genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=Tier2DiagnosisResult,
                temperature=0.15,
            )
            resp, used_model, attempts = await self._call_genai_with_retry(
                stage="T2_DIAGNOSIS",
                model_candidates=[
                    self.settings.tier2_primary_model,
                    self.settings.tier2_fallback_model,
                ],
                contents=[image_part, prompt],
                config=cfg,
                timeout_sec=10.0,
            )
            if resp and used_model and getattr(resp, "text", None):
                try:
                    data = json.loads(resp.text)
                    data["incident_id"] = incident_id
                    if matched_sops and data.get("matched_sop_id") not in {s.id for s in matched_sops}:
                        data["matched_sop_id"] = matched_sops[0].id
                    data["skill_applied"] = skill_name
                    diagnosis = Tier2DiagnosisResult(**data)
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                    prov = StageProvenance(
                        stage="T2_DIAGNOSIS",
                        producer="MODEL" if used_model == self.settings.tier2_primary_model else "FALLBACK_MODEL",
                        model_id=used_model,
                        attempts=attempts,
                        latency_ms=elapsed_ms,
                        input_simulated=input_simulated,
                    )
                    return diagnosis, prov
                except Exception:
                    if attempts:
                        attempts[-1].status = "SCHEMA_INVALID"

        self.metrics.record_fallback_used("T2_DIAGNOSIS")
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        sop_id = top_sop.id if top_sop else "SOP-UNMATCHED"
        diagnosis = Tier2DiagnosisResult(
            incident_id=incident_id,
            defect_type="OTHER",
            defect_class="Escalated anomaly — rule-based fallback (AI model unavailable)",
            severity="MEDIUM",
            confidence=0.0,
            root_cause_analysis=(
                "Tier-2 AI model was unavailable. Hold part for quality engineer review "
                f"and follow retrieved reference {sop_id}."
            ),
            matched_sop_id=sop_id,
            skill_applied=skill_name,
            recommended_disposition="HOLD",
            repair_steps=[
                "Quarantine part and notify shift Quality Engineer.",
                f"Review retrieved SOP {sop_id} before adjusting any machine parameters.",
            ],
            safety_precautions=[
                "Follow machine LOTO / ESD procedure prior to physical inspection.",
                "Do not resume production until QE records a disposition.",
            ],
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
        """Tier-4 Co-Pilot using gemini-3.8-live with truthful text fallback."""
        t0 = time.perf_counter()
        attempts: list[ModelAttempt] = []
        prompt = (
            f"Answer in {request.language}, max 3 short sentences, cite SOP {matched_sop.id}, "
            "and only use values from the SOP.\n"
            f"SOP [{matched_sop.id}] ({matched_sop.title}): {matched_sop.sop_markdown}\n"
            f"Torque / Calibration Spec: {matched_sop.torque_spec}\n"
            f"Question: {request.question}"
        )

        if not force_fallback and self._client is not None and genai_types is not None:
            t_live = time.perf_counter()
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
                        async for msg in session.receive():
                            sc = getattr(msg, "server_content", None)
                            if (
                                sc
                                and getattr(sc, "output_transcription", None)
                                and sc.output_transcription.text
                            ):
                                transcript_chunks.append(sc.output_transcription.text)
                            if sc and getattr(sc, "turn_complete", False):
                                break
                        live_text = "".join(transcript_chunks).strip()
                        live_ms = int((time.perf_counter() - t_live) * 1000)
                        if live_text:
                            att = ModelAttempt(
                                model_id=self.settings.tier4_live_copilot_model,
                                status="OK",
                                latency_ms=live_ms,
                            )
                            attempts.append(att)
                            self.metrics.record_attempt(self.settings.tier4_live_copilot_model, "OK", live_ms)
                            _log_attempt_json("T4_COPILOT", att)
                            elapsed_ms = int((time.perf_counter() - t0) * 1000)
                            prov = StageProvenance(
                                stage="T4_COPILOT",
                                producer="MODEL",
                                model_id=self.settings.tier4_live_copilot_model,
                                attempts=attempts,
                                latency_ms=elapsed_ms,
                                input_simulated=False,
                            )
                            return CopilotChatResponse(
                                answer=live_text,
                                model_used=self.settings.tier4_live_copilot_model,
                                producer="MODEL",
                                grounded_sop_id=matched_sop.id,
                                latency_ms=elapsed_ms,
                                provenance=prov,
                            )
            except Exception as exc:
                live_ms = int((time.perf_counter() - t_live) * 1000)
                status, err_msg = _classify_exception(exc)
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
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                prov = StageProvenance(
                    stage="T4_COPILOT",
                    producer="FALLBACK_MODEL",
                    model_id=used_model,
                    attempts=attempts,
                    latency_ms=elapsed_ms,
                    input_simulated=False,
                    note="TEXT FALLBACK (Live unavailable)",
                )
                return CopilotChatResponse(
                    answer=resp.text.strip(),
                    model_used=used_model,
                    producer="FALLBACK_MODEL",
                    grounded_sop_id=matched_sop.id,
                    latency_ms=elapsed_ms,
                    provenance=prov,
                )

        self.metrics.record_fallback_used("T4_COPILOT")
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        fallback_answer = (
            f"[{matched_sop.id}] {matched_sop.sop_markdown} "
            f"Spec: {matched_sop.torque_spec}."
        )
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
            model_used=None,
            producer="FALLBACK_RULES",
            grounded_sop_id=matched_sop.id,
            latency_ms=elapsed_ms,
            provenance=prov,
        )
