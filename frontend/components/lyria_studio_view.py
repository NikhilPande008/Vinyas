"""
frontend/components/lyria_studio_view.py
Lyria Fault Harmonic Studio View:
Isolated via @st.fragment for live pitch judge stress-testing and Day-1 calibration.
Allows judges and plant heads to inject synthetic structural fault harmonics:
- 4,210 Hz Flank Wear Regenerative Chatter
- External Wrench-Strike Floor Shock (Demonstrates ct_ripple_std < 0.12 A false-positive rejection)
- Spindle Bearing Outer Race Spall (BPFO 184 Hz)
- Nominal Baseline Cut
"""
import base64
from typing import Any, Optional
import httpx
import streamlit as st
from config.settings import settings
from backend.services.lyria_synth_service import LyriaSynthService

lyria_service = LyriaSynthService()


def _synthesize_or_fallback(backend_url: str, fault_type: str) -> tuple[bytes, dict[str, Any]]:
    try:
        with httpx.Client(timeout=3.0) as client:
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


@st.fragment
def render_lyria_studio_view(backend_url: str = "http://localhost:8000"):
    """Renders the isolated fault harmonic injection studio."""
    st.markdown("### 🎚️ Lyria Acoustic Studio & Fault Injector")
    st.caption("Zero-Downtime Sensor Calibration & Live Judge Stress-Testing Panel (Lyria / Stereo 48 kHz Stems)")

    st.info(
        "💡 **Judge Calibration Tool:** Demonstrates how factories calibrate edge preemption models "
        "on Day 1 without intentionally crashing a ₹40 Lakh CNC spindle."
    )

    c1, c2, c3, c4 = st.columns(4)

    active_fault = "CHATTER_4210HZ"
    with c1:
        if st.button("⚡ 4,210 Hz Tool Chatter", use_container_width=True, type="primary"):
            active_fault = "CHATTER_4210HZ"
    with c2:
        if st.button("🔨 Wrench Strike Test", use_container_width=True):
            active_fault = "WRENCH_STRIKE"
    with c3:
        if st.button("⚙️ Bearing Spall (184 Hz)", use_container_width=True):
            active_fault = "BEARING_SPALLING"
    with c4:
        if st.button("🟢 Nominal PPAP Cut", use_container_width=True):
            active_fault = "NOMINAL_CUT"

    fault_selection = st.radio(
        "Or select waveform stem to inspect:",
        [
            "CHATTER_4210HZ: 4,210 Hz Flank Wear Regenerative Chatter",
            "WRENCH_STRIKE: External Floor Shock / Wrench Drop (False-Positive Test)",
            "BEARING_SPALLING: Spindle Bearing Outer-Race Defect (BPFO 184 Hz)",
            "NOMINAL_CUT: Nominal ISO Machining Baseline",
        ],
        index=0,
    )
    stem_type = fault_selection.split(":")[0]

    with st.spinner("Synthesizing stereo 48 kHz waveform stem..."):
        wav_bytes, meta = _synthesize_or_fallback(backend_url, stem_type)

    st.markdown("---")
    col_meta, col_audio = st.columns([1.2, 1.0], gap="large")

    with col_meta:
        st.markdown(f"#### Stem Analysis: `{meta.get('fault_type', stem_type)}`")
        st.markdown(f"**Description:** {meta.get('description', '')}")
        st.markdown(f"**Target Tool Station:** `{meta.get('target_tool', 'T03')}`")

        pred_state = meta.get("predicted_stage_a_state", "YELLOW_M01_HOLD")
        if pred_state == "YELLOW_M01_HOLD":
            st.warning(f"**Predicted Edge Action:** `YELLOW_M01_HOLD` (Sub-1.4 ms Preemption)")
        elif pred_state == "GREEN_FALSE_POSITIVE_REJECTED":
            st.success(f"**Predicted Edge Action:** `GREEN_FALSE_POSITIVE_REJECTED` (Floor Shock Ignored)")
        else:
            st.info(f"**Predicted Edge Action:** `{pred_state}`")

    with col_audio:
        st.markdown("#### 🎧 Stereo 48 kHz Audio Stem")
        st.caption("Ch0 (Left): Spindle Piezo AE | Ch1 (Right): Clamped Motor Current CT")
        st.audio(wav_bytes, format="audio/wav")

        st.caption("Layered over authentic Pune-Chakan ambient machinery hum.")
