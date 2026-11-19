"""
frontend/components/fault_injection_studio_view.py
Vinyas Fault Injection Studio View:
Isolated via @st.fragment for live Pune City Buildathon judge stress-testing:
1. Injects 48 kHz stereo stems (4,210 Hz Chatter, Light Finishing Cut, External Wrench Strike,
   Bearing Outer-Race Spall, Nominal Cut) directly through `stage_a_deterministic_fast_path()`
   to prove real-time CPU latency (<1.4 ms), 2-8 kHz vibration band ratio, and wrench immunity.
2. Day-0 Synthetic Defect Calibration via Nano Banana Pro (`gemini-3-pro-image-preview`).
"""
import asyncio
import base64
import io
import multiprocessing as mp
from pathlib import Path
from typing import Any
import httpx
import numpy as np
from scipy.io import wavfile
import streamlit as st
from config.settings import settings
from edge.hardware_relay import HardwareRelayController
from edge.hilbert_envelope_dsp import stage_a_deterministic_fast_path
from backend.services.lyria_synth_service import LyriaSynthService
from backend.services.nanobanana_aoi_service import NanoBananaAOIService

lyria_service = LyriaSynthService()
aoi_synth_service = NanoBananaAOIService()


def _synthesize_or_fallback(backend_url: str, fault_type: str) -> tuple[bytes, dict[str, Any]]:
    try:
        with httpx.Client(timeout=2.5) as client:
            resp = client.post(
                f"{backend_url}/api/v1/faults/synthesize",
                json={"fault_type": fault_type, "duration_sec": 2.0},
            )
            if resp.status_code == 200:
                data = resp.json()
                wav_bytes = base64.b64decode(data.get("wav_b64", ""))
                return wav_bytes, data.get("metadata", {})
    except Exception:
        pass
    return lyria_service.synthesize_fault_stem(fault_type, duration_sec=2.0)


def _evaluate_injected_wav_stage_a(wav_bytes: bytes) -> dict[str, Any]:
    fs, data = wavfile.read(io.BytesIO(wav_bytes))
    if data.dtype == np.int16:
        data = (data / 32768.0).astype(np.float32)
    else:
        data = data.astype(np.float32)
    start_idx = 24000 if len(data) >= 36000 else 0
    chunk = data[start_idx : start_idx + 12000, :]
    relay = HardwareRelayController()
    q = mp.Queue()
    return stage_a_deterministic_fast_path(chunk, relay, q, {"tool_id": "T03", "pass_type": "FINISHING"})


@st.fragment
def render_fault_injection_studio_view(backend_url: str = "http://localhost:8000"):
    """Renders the isolated Fault Injection & Nano Banana Pro Day-0 Calibration Studio."""
    st.markdown("### 🎚️ Vinyas Fault Injection Studio & Day-0 Calibration")
    st.caption(
        "Live Stereo 48 kHz Edge DSP Loopback + Nano Banana Pro (`gemini-3-pro-image-preview`) Day-0 Defect Synthesis"
    )

    tab_acoustic, tab_visual = st.tabs(
        ["⚡ Stereo 48 kHz Fault Injection", "🧪 Day-0 Synthetic Defect Calibration (Nano Banana Pro)"]
    )

    with tab_acoustic:
        fault_selection = st.radio(
            "Select 48 kHz Stereo Waveform Stem to Inject into Stage A DSP:",
            [
                "CHATTER_4210HZ: 4,210 Hz Flank Wear Regenerative Chatter (Ch 0 + Ch 1 Coupled)",
                "WRENCH_STRIKE: External Table Shock / Wrench Drop (False-Positive Immunity Test)",
                "BEARING_SPALLING: Spindle Bearing Outer-Race Defect (BPFO 184 Hz)",
                "NOMINAL_CUT: Nominal ISO Machining Baseline",
            ],
            index=0,
        )
        stem_type = fault_selection.split(":")[0]

        with st.spinner("Synthesizing stereo 48 kHz stem & running Stage A DSP loopback..."):
            wav_bytes, meta = _synthesize_or_fallback(backend_url, stem_type)
            dsp_live = _evaluate_injected_wav_stage_a(wav_bytes)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Triggered State", dsp_live.get("stage_a_state", "GREEN_NOMINAL"))
        c2.metric("Stage A CPU Latency", f"{dsp_live.get('latency_ms', 0.0):.2f} ms", "< 1.4 ms target")
        c3.metric("2-8 kHz Band Ratio", f"{dsp_live.get('band_power_ratio_2k_8k', 0.0):.2f}")
        c4.metric("Envelope Coherence", f"{dsp_live.get('coherence', 0.0):.2f}")

        st.markdown("---")
        col_meta, col_audio = st.columns([1.2, 1.0], gap="large")
        with col_meta:
            st.markdown(f"#### Stem Diagnostics: `{meta.get('fault_type', stem_type)}`")
            st.markdown(f"**Detection Source:** `{dsp_live.get('detection_source', 'NOMINAL')}`")
            st.markdown(
                f"**Peak Vib RMS:** `{dsp_live.get('ae_rms_g', 0.0):.2f} G` | "
                f"**CT Ripple Std:** `{dsp_live.get('ct_ripple_std_amps', 0.0):.3f} A` | "
                f"**Spectral Crest:** `{dsp_live.get('spectral_crest_factor', 0.0):.1f}`"
            )
            st.caption(meta.get("description", ""))
        with col_audio:
            st.markdown("#### 🎧 Stereo 48 kHz Audio Preview")
            st.caption("Ch 0 (Left): Piezo Vibration | Ch 1 (Right): Split-Core CT")
            st.audio(wav_bytes, format="audio/wav")

    with tab_visual:
        st.markdown("#### Day-0 Synthetic Defect Generation from Golden Master (`REF-01`)")
        st.caption(f"Model: `{settings.GEMINI_IMAGE_MODEL_ID}` (Nano Banana Pro)")
        defect_choice = st.selectbox(
            "Target Synthetic Defect Class:",
            ["MICRO_BURR_REJECT", "CHATTER_SCAR_REJECT", "FOUNDRY_POROSITY_CHARGEBACK"],
            index=0,
        )
        if st.button("✨ GENERATE DAY-0 SYNTHETIC DEFECT EXEMPLAR", type="primary"):
            golden_path = Path("data/golden_references/REF-01.jpg")
            if golden_path.exists():
                synth_bytes = asyncio.run(
                    aoi_synth_service.synthesize_cold_start_defect(
                        base_golden_jpeg_bytes=golden_path.read_bytes(),
                        defect_type=defect_choice,
                    )
                )
                g_col, s_col = st.columns(2)
                g_col.image(str(golden_path), caption="Golden Master Input (REF-01)", use_container_width=True)
                s_col.image(synth_bytes, caption=f"Nano Banana Pro Synthesized ({defect_choice})", use_container_width=True)
