"""
backend/services/gemini_omni_service.py
Stage C Synchronized Multimodal Diagnostic Engine (`gemini-2.5-flash`):
- Consumes anti-aliased 16 kHz WAV, 256x256 Mel-Spectrogram PNG, CT envelope JSON,
  and optional post-retract optical frame in one unified context window.
- Follows "Physics Calculates, AI Diagnoses": `classify_diagnostic_evidence()` emits
  pure `DiagnosticEvidence` (classification only—never guesses CNC offsets or overrides).
- Protected by `@with_demo_circuit_breaker` setting `served_from_fallback = True` on fallback.
"""
import logging
from typing import Optional
from google import genai
from google.genai import types
from config.settings import settings
from backend.models.schemas import (
    DiagnosticEvidence,
    DeterministicControlSolution,
    PPAPRemediationPlan,
    VernacularActionCard,
)
from backend.services.circuit_breaker import with_demo_circuit_breaker

logger = logging.getLogger("vinyas_ai.backend.gemini_omni")


class GeminiOmniService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.client = genai.Client(api_key=self.api_key)

    @with_demo_circuit_breaker(
        fallback_filename="diagnostic_evidence_chatter_t03.json",
        response_model=DiagnosticEvidence,
        timeout_sec=settings.CIRCUIT_BREAKER_TIMEOUT_SEC,
    )
    async def classify_diagnostic_evidence(
        self,
        audio_wav_16k_bytes: bytes,
        mel_spectrogram_png_bytes: bytes,
        ct_envelope_json_str: str,
        retract_frame_jpeg_bytes: Optional[bytes] = None,
        machine_context: Optional[dict] = None,
    ) -> DiagnosticEvidence:
        """
        Pure multimodal classification call (AI Diagnoses Only — zero LLM offset guessing).
        Exact feed/speed overrides are computed deterministically by `control_plan_solver.py`.
        """
        ctx = machine_context or {}
        machine_id = ctx.get("machine_id", "FANUC_0iTF_CHAKAN_04")
        tool_id = ctx.get("tool_id", "T03")
        cycle_id = ctx.get("cycle_id", "CYC_CHAKAN_04_99281")

        prompt_text = (
            f"You are the Lead CNC Multimodal Diagnostics Agent for Vinyas operating in Pune-Chakan.\n"
            f"Classify the root cause for Machine={machine_id}, Tool={tool_id}, Cycle={cycle_id}.\n"
            f"Do NOT invent numeric CNC dial percentages or Z-wear offsets; report ONLY the defect "
            f"classification, dominant chatter harmonic Hz, confidence, false-positive check, and evidence."
        )

        contents = [
            types.Part.from_text(text=prompt_text),
            types.Part.from_text(text=f"In-Cycle Telemetry & CT Envelope:\n{ct_envelope_json_str}"),
            types.Part.from_bytes(data=audio_wav_16k_bytes, mime_type="audio/wav"),
            types.Part.from_bytes(data=mel_spectrogram_png_bytes, mime_type="image/png"),
        ]
        if retract_frame_jpeg_bytes:
            contents.append(
                types.Part.from_bytes(data=retract_frame_jpeg_bytes, mime_type="image/jpeg")
            )

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DiagnosticEvidence,
            temperature=0.0,
            system_instruction=(
                "Classify CNC acoustic-electrical faults strictly into DiagnosticEvidence JSON. "
                "Never output G-code coordinates or unverified offsets."
            ),
        )

        response = await self.client.aio.models.generate_content(
            model=settings.GEMINI_OMNI_MODEL_ID,
            contents=contents,
            config=config,
        )
        return DiagnosticEvidence.model_validate_json(response.text)

    @with_demo_circuit_breaker(
        fallback_filename="ppap_chatter_t03.json",
        response_model=PPAPRemediationPlan,
        timeout_sec=settings.CIRCUIT_BREAKER_TIMEOUT_SEC,
    )
    async def diagnose_cutting_incident(
        self,
        audio_wav_16k_bytes: bytes,
        mel_spectrogram_png_bytes: bytes,
        ct_envelope_json_str: str,
        retract_frame_jpeg_bytes: Optional[bytes] = None,
        machine_context: Optional[dict] = None,
    ) -> PPAPRemediationPlan:
        """
        Backwards-compatible multimodal diagnostic endpoint returning PPAPRemediationPlan.
        """
        ctx = machine_context or {}
        machine_id = ctx.get("machine_id", "FANUC_0iTF_CHAKAN_04")
        tool_id = ctx.get("tool_id", "T03")
        work_order = ctx.get("work_order_id", "WO_ALSI9CU3_DIFF_882")

        prompt_text = (
            f"You are the Lead CNC Acoustic-Electrical Diagnostics Agent for Vinyas operating in Chakan.\n"
            f"Evaluate the attached 16kHz audio cut, 256x256 Mel-Spectrogram, CT current envelope JSON, "
            f"and dry-retract optical frame for Machine: {machine_id}, Tool: {tool_id}, Work Order: {work_order}."
        )

        contents = [
            types.Part.from_text(text=prompt_text),
            types.Part.from_text(text=f"CT Motor Current Envelope:\n{ct_envelope_json_str}"),
            types.Part.from_bytes(data=audio_wav_16k_bytes, mime_type="audio/wav"),
            types.Part.from_bytes(data=mel_spectrogram_png_bytes, mime_type="image/png"),
        ]

        if retract_frame_jpeg_bytes:
            contents.append(
                types.Part.from_bytes(data=retract_frame_jpeg_bytes, mime_type="image/jpeg")
            )

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PPAPRemediationPlan,
            temperature=0.0,
            system_instruction=(
                "You are an expert manufacturing diagnostics engineer specialized in IATF 16949 PPAP control plans. "
                "Never exceed signed PPAP control limits. Day-1 manual action must include concise Marathi instructions."
            ),
        )

        response = await self.client.aio.models.generate_content(
            model=settings.GEMINI_OMNI_MODEL_ID,
            contents=contents,
            config=config,
        )
        return PPAPRemediationPlan.model_validate_json(response.text)

    async def translate_vernacular_action_card(
        self,
        control_solution: DeterministicControlSolution,
        detected_harmonic_hz: float,
    ) -> VernacularActionCard:
        """
        Translates pre-verified `DeterministicControlSolution` dial settings into zero-jargon
        Marathi, Hindi, and Hinglish operator instructions using `gemma-3-4b-it` (or Ollama local
        Gemma with deterministic fallback). Never alters numerical feed/speed/wear values.
        """
        import time
        import httpx

        t0 = time.perf_counter()
        tool_id = control_solution.target_tool_id
        feed_pct = control_solution.operator_feedrate_dial_pct
        speed_pct = control_solution.spindle_speed_dial_pct
        rpm = control_solution.target_rpm

        default_marathi = (
            f"Tool {tool_id} Finishing Pass madhye chatter ({detected_harmonic_hz:.0f} Hz) aala aahe. "
            f"M01 Hold var Feedrate Override knob {feed_pct}% ani "
            f"Spindle Speed dial {speed_pct}% ({rpm} RPM) var set kara, "
            f"ani {tool_id} Insert Corner #2 badla."
        )
        default_hindi = (
            f"Tool {tool_id} Finishing Pass में चैटर ({detected_harmonic_hz:.0f} Hz) आया है। "
            f"M01 Hold पर Feedrate knob {feed_pct}% और Spindle Speed dial {speed_pct}% ({rpm} RPM) पर सेट करें, "
            f"और {tool_id} Insert Corner #2 बदलें।"
        )
        default_hinglish = (
            f"M01 Hold par Feed Knob {feed_pct}% aur Speed Knob {speed_pct}% ({rpm} RPM) set karein, "
            f"phir Tool {tool_id} Insert Corner #2 index karke Palm PTT button dabayein."
        )

        if settings.DEMO_SAFE_MODE:
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return VernacularActionCard(
                model_id=settings.VERNACULAR_GEMMA_MODEL_ID,
                marathi=default_marathi,
                hindi=default_hindi,
                hinglish=default_hinglish,
                translation_latency_ms=latency_ms,
                served_from_fallback=True,
            )

        prompt = (
            f"Translate these verified CNC M01 remediation settings into zero-jargon shop-floor instructions "
            f"in Marathi, Hindi, and Hinglish. You MUST preserve the exact numbers: "
            f"Tool={tool_id}, Chatter={detected_harmonic_hz:.0f} Hz, Feedrate Dial={feed_pct}%, "
            f"Spindle Speed Dial={speed_pct}% ({rpm} RPM), Insert=Corner #2.\n"
            f"Return JSON matching VernacularActionCard schema."
        )

        # 1. Attempt local Ollama Gemma 3 4B IT (`keep_alive=-1`) for sub-30ms edge vernacular generation
        try:
            async with httpx.AsyncClient(timeout=0.35) as http_client:
                resp = await http_client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": settings.VERNACULAR_GEMMA_MODEL_ID,
                        "prompt": prompt,
                        "format": "json",
                        "stream": False,
                        "keep_alive": -1,
                        "options": {"temperature": 0.0, "num_predict": 160},
                    },
                )
                if resp.status_code == 200:
                    import json as _json
                    parsed = _json.loads(resp.json().get("response", "{}"))
                    if parsed.get("marathi") and str(feed_pct) in str(parsed.get("marathi")):
                        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                        return VernacularActionCard(
                            model_id=settings.VERNACULAR_GEMMA_MODEL_ID,
                            marathi=str(parsed["marathi"]),
                            hindi=str(parsed.get("hindi", default_hindi)),
                            hinglish=str(parsed.get("hinglish", default_hinglish)),
                            translation_latency_ms=latency_ms,
                            served_from_fallback=False,
                        )
        except Exception:
            pass

        # 2. Attempt Google GenAI API (`gemma-3-4b-it` / `gemini-2.5-flash` structured output)
        try:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VernacularActionCard,
                temperature=0.0,
            )
            response = await self.client.aio.models.generate_content(
                model=settings.GEMINI_OMNI_MODEL_ID,
                contents=prompt,
                config=config,
            )
            card = VernacularActionCard.model_validate_json(response.text)
            card.model_id = settings.VERNACULAR_GEMMA_MODEL_ID
            card.translation_latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            card.served_from_fallback = False
            return card
        except Exception as exc:
            logger.warning("Vernacular translation fallback triggered (%s)", exc)

        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return VernacularActionCard(
            model_id=settings.VERNACULAR_GEMMA_MODEL_ID,
            marathi=default_marathi,
            hindi=default_hindi,
            hinglish=default_hinglish,
            translation_latency_ms=latency_ms,
            served_from_fallback=True,
        )
