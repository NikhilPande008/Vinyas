"""
backend/agents/extractor_agent.py
DiagnosticExtractorAgent (Column 1 of Antigravity Verification Trace):
Combines Stage A DSP telemetry, Stage B Gemma triage, 256x256 Mel-Spectrogram,
anti-aliased 16 kHz RIFF WAVE audio bundle, and BigQuery + 1408-d NumPy cosine
similarity matching to diagnose root cause.
"""
import base64
import logging
from typing import Optional
import numpy as np
from backend.models.schemas import (
    MultimodalIncidentPayload,
    VectorSearchMatch,
)
from backend.services.gemini_omni_service import GeminiOmniService
from backend.services.vector_search_service import VectorSearchService
from edge.hilbert_envelope_dsp import (
    encode_16khz_wav_bytes,
    render_mel_spectrogram_png_bytes,
)

logger = logging.getLogger("vinyas_ai.agents.extractor")


class DiagnosticExtractorAgent:
    def __init__(
        self,
        vector_service: Optional[VectorSearchService] = None,
        omni_service: Optional[GeminiOmniService] = None,
    ):
        self.vector_service = vector_service or VectorSearchService()
        self.omni_service = omni_service or GeminiOmniService()

    @staticmethod
    def build_stereo_window_from_telemetry(
        dominant_carrier_hz: float,
        modulation_sideband_hz: float,
        ae_rms_g: float,
        ct_ripple_std_amps: float,
    ) -> np.ndarray:
        """Synthesizes a physically calibrated (12000, 2) 48 kHz stereo waveform matching measured telemetry."""
        t = np.linspace(0, 0.25, 12000, endpoint=False, dtype=np.float32)
        ae_amp = max(min(ae_rms_g / 10.0, 0.85), 0.05)
        ct_amp = max(min(ct_ripple_std_amps / 15.0, 0.50), 0.01)
        ch0 = (
            ae_amp
            * (1.0 + 0.55 * np.sin(2.0 * np.pi * modulation_sideband_hz * t))
            * np.sin(2.0 * np.pi * dominant_carrier_hz * t)
        )
        ch1 = ct_amp * np.sin(2.0 * np.pi * modulation_sideband_hz * t) + 0.02 * np.sin(
            2.0 * np.pi * 50.0 * t
        )
        return np.column_stack([ch0, ch1]).astype(np.float32)

    async def extract_and_match_bundle(
        self,
        incident: MultimodalIncidentPayload,
        stereo_chunk_raw: Optional[np.ndarray] = None,
    ) -> tuple[VectorSearchMatch, str, bytes, bytes]:
        """
        Queries BigQuery + 1408-d NumPy cosine cache, renders the 256x256 Mel-Spectrogram PNG,
        and encodes the anti-aliased 16 kHz RIFF WAVE audio bytes for Gemini 2.5 Flash.
        Returns (VectorSearchMatch, mel_spectrogram_b64, mel_png_bytes, audio_wav_16k_bytes).
        """
        dsp = incident.stage_a_dsp_telemetry

        # 1. Query BigQuery + 1408-d in-memory NumPy cosine index (<0.5 ms)
        match = await self.vector_service.query_nearest_signature(
            dominant_carrier_hz=dsp.dominant_carrier_freq_hz,
            hilbert_coherence=dsp.hilbert_envelope_coherence,
            ae_rms=dsp.ae_rms_g,
        )

        # 2. Ensure valid (12000, 2) 48 kHz stereo window for spectrogram & 16 kHz WAV encoding
        if stereo_chunk_raw is not None and stereo_chunk_raw.shape == (12000, 2):
            effective_stereo = stereo_chunk_raw.astype(np.float32)
        else:
            effective_stereo = self.build_stereo_window_from_telemetry(
                dominant_carrier_hz=dsp.dominant_carrier_freq_hz,
                modulation_sideband_hz=dsp.modulation_sideband_hz,
                ae_rms_g=dsp.ae_rms_g,
                ct_ripple_std_amps=dsp.ct_ripple_std_amps,
            )

        png_bytes = render_mel_spectrogram_png_bytes(
            stereo_chunk_250ms=effective_stereo,
            coherence_score=dsp.hilbert_envelope_coherence,
            carrier_hz=dsp.dominant_carrier_freq_hz,
        )
        wav_16k_bytes = encode_16khz_wav_bytes(effective_stereo)
        mel_b64 = base64.b64encode(png_bytes).decode("utf-8")
        return match, mel_b64, png_bytes, wav_16k_bytes

    async def extract_and_match(
        self,
        incident: MultimodalIncidentPayload,
        stereo_chunk_raw: Optional[np.ndarray] = None,
    ) -> tuple[VectorSearchMatch, str]:
        """Backwards-compatible wrapper returning (VectorSearchMatch, mel_spectrogram_b64)."""
        match, mel_b64, _png, _wav = await self.extract_and_match_bundle(incident, stereo_chunk_raw)
        return match, mel_b64
