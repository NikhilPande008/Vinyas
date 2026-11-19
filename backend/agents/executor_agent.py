"""
backend/agents/executor_agent.py
ShopFloorExecutorAgent:
Handles vernacular voice interaction from the shop floor palm-button PTT pod.
Enforces the SanitizedVoiceIntent schema gate before recording shift state changes
and streaming verified entries into BigQuery.
"""
import logging
from typing import Optional
from backend.models.schemas import SanitizedVoiceIntent
from backend.services.bigquery_logger import BigQueryLogger
from backend.services.gemini_live_service import GeminiLiveService

logger = logging.getLogger("vinyas_ai.agents.executor")


class ShopFloorExecutorAgent:
    def __init__(
        self,
        live_service: Optional[GeminiLiveService] = None,
        bigquery_logger: Optional[BigQueryLogger] = None,
    ):
        self.live_service = live_service or GeminiLiveService()
        self.bigquery_logger = bigquery_logger or BigQueryLogger()

    async def execute_operator_voice_command(
        self,
        operator_speech_text: str,
        active_incident_context: Optional[dict] = None,
    ) -> SanitizedVoiceIntent:
        """
        Processes operator voice input, validates sanitized intent,
        and logs state resolution to BigQuery ledger.
        """
        intent = await self.live_service.process_operator_utterance(operator_speech_text)

        if intent.intent == "CONFIRM_INSERT_SWAP":
            ctx = active_incident_context or {}
            await self.bigquery_logger.log_incident(
                {
                    "event_id": ctx.get("event_id", "evt_manual_action"),
                    "machine_id": ctx.get("machine_id", "FANUC_0iTF_CHAKAN_04"),
                    "tool_id": ctx.get("tool_id", "T03"),
                    "state": "ACTION_CONFIRMED_GREEN",
                    "coherence": 0.0,
                    "ppap_passed": True,
                    "estimated_savings_inr": ctx.get("estimated_savings_inr", 16200),
                    "cycle_time_penalty_sec": ctx.get("cycle_time_penalty_sec", 4.2),
                    "operator_voice_confirmation": intent.spoken_response_marathi,
                }
            )

        return intent
