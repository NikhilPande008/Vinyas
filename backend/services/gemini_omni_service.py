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
from backend.models.schemas import DiagnosticEvidence, PPAPRemediationPlan
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
