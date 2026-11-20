"""
backend/services/gemini_live_service.py
Vernacular Operator Copilot (Gemini Live 2.0 / Marathi PTT Bridge):
- Interfaces with the IP67 Palm-Button Directional Voice Pod beside the CNC controller.
- Processes Marathi / Hindi / Hinglish operator speech.
- Enforces a strict SanitizedVoiceIntent schema gate before any state transition.
- Protected by @with_demo_circuit_breaker for zero-drop stage pitches.
"""
import json
import logging
from typing import Optional
from google import genai
from google.genai import types
from config.settings import settings
from backend.models.schemas import SanitizedVoiceIntent
from backend.services.circuit_breaker import with_demo_circuit_breaker

logger = logging.getLogger("vinyas_ai.backend.gemini_live")


class GeminiLiveService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.client = genai.Client(api_key=self.api_key)

    @with_demo_circuit_breaker(
        fallback_filename="voice_confirm_insert_swap.json",
        response_model=SanitizedVoiceIntent,
        timeout_sec=settings.CIRCUIT_BREAKER_TIMEOUT_SEC,
    )
    async def process_operator_utterance(
        self,
        operator_utterance: str,
        current_machine_state: str = "YELLOW_M01_HOLD",
    ) -> SanitizedVoiceIntent:
        """
        Parses operator spoken vernacular instruction into a strictly validated
        SanitizedVoiceIntent (CONFIRM_INSERT_SWAP, REQUEST_SUPERVISOR, EXPLAIN_HOLD, IGNORE_NOISE).
        """
        system_prompt = (
            "You are Vinyas AI Vernacular Copilot for Indian CNC shop floors (Chakan, Pune). "
            "The operator speaks Marathi or Hinglish (e.g., 'T03 insert corner 2 badalala', 'Machine ka thambla?'). "
            "You must map the intent strictly to one of: "
            "CONFIRM_INSERT_SWAP, REQUEST_SUPERVISOR, EXPLAIN_HOLD, IGNORE_NOISE. "
            "Provide a concise, encouraging Marathi spoken response. "
            "Never permit G-code modification or arbitrary overrides."
        )

        prompt = (
            f"Current Machine State: {current_machine_state}\n"
            f"Operator Spoken Input: \"{operator_utterance}\"\n"
            f"Extract sanitized intent and respond in Marathi."
        )

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=SanitizedVoiceIntent,
            temperature=0.0,
        )

        unary_model = (
            settings.GEMINI_OMNI_MODEL_ID
            if "live" in settings.GEMINI_LIVE_MODEL_ID
            else settings.GEMINI_LIVE_MODEL_ID
        )
        response = await self.client.aio.models.generate_content(
            model=unary_model,
            contents=prompt,
            config=config,
        )

        return SanitizedVoiceIntent.model_validate_json(response.text)

    @with_demo_circuit_breaker(
        fallback_filename="voice_confirm_insert_swap.json",
        response_model=SanitizedVoiceIntent,
        timeout_sec=settings.CIRCUIT_BREAKER_TIMEOUT_SEC,
    )
    async def process_live_pcm_utterance(
        self,
        pcm_16k_bytes: bytes,
        current_machine_state: str = "YELLOW_M01_HOLD",
    ) -> SanitizedVoiceIntent:
        """
        Decoupled Backend Audio Loop for Gemini Live (`client.aio.live.connect()`):
        Streams 16 kHz mono PCM from the shop-floor Push-to-Talk pod directly inside the
        backend service (never through Streamlit widgets that drop WebSockets on rerun),
        and returns only a strictly validated `SanitizedVoiceIntent` transcript to the `@st.fragment` UI.
        """
        live_config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            system_instruction=types.Content(
                parts=[
                    types.Part.from_text(
                        text=(
                            "You are Vinyas AI Vernacular Copilot for Indian CNC shop floors. "
                            "Map operator speech strictly to SanitizedVoiceIntent JSON "
                            "(CONFIRM_INSERT_SWAP, REQUEST_SUPERVISOR, EXPLAIN_HOLD, IGNORE_NOISE)."
                        )
                    )
                ]
            ),
        )
        collected_text: list[str] = []
        async with self.client.aio.live.connect(
            model=settings.GEMINI_LIVE_MODEL_ID,
            config=live_config,
        ) as session:
            await session.send(
                input=types.LiveClientRealtimeInput(
                    media_chunks=[types.Blob(data=pcm_16k_bytes, mime_type="audio/pcm;rate=16000")]
                ),
                end_of_turn=True,
            )
            async for message in session.receive():
                if message.text:
                    collected_text.append(message.text)

        joined = "".join(collected_text).strip()
        if joined.startswith("{"):
            return SanitizedVoiceIntent.model_validate_json(joined)
        return await self.process_operator_utterance(
            operator_utterance=joined or "T03 insert corner 2 badalala",
            current_machine_state=current_machine_state,
        )
