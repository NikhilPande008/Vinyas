"""
frontend/components/lyria_studio_view.py
Vinyas Fault Calibration & Demo Studio (Persona 4: Plant Onboarding & Live Judge Stress-Testing):
Isolated via @st.fragment.
- Replaces plain radio buttons with 4 tactile scenario trigger cards showing each stem's acoustic/current signature:
  1. Chatter 4210 Hz (CHATTER_4210HZ)
  2. Wrench Strike False-Positive (WRENCH_STRIKE)
  3. Bearing Spall (BEARING_SPALLING)
  4. Nominal Cut (NOMINAL_CUT)
- Replaces cramped st.metric widgets with un-truncated responsive flex KPI cards (`Stage A DSP: 1.12 ms`)
- Renders a real-time dual-channel oscilloscope preview (`Ch 0 Piezo AE` vs `Ch 1 Split-Core CT`)
  plus stereo 48 kHz audio playback and Nano Banana Pro Day-0 synthetic defect calibration.
"""
import asyncio
import base64
import io
import multiprocessing as mp
from pathlib import Path
from typing import Any
import httpx
import numpy as np
from PIL import Image, ImageDraw
from scipy.io import wavfile
import streamlit as st
from config.settings import settings
from edge.hardware_relay import HardwareRelayController
from edge.hilbert_envelope_dsp import (
    VIBRATION_G_PER_FS,
    CT_AMPS_PER_FS,
    stage_a_deterministic_fast_path,
)
from backend.services.lyria_synth_service import LyriaSynthService
from backend.services.nanobanana_aoi_service import NanoBananaAOIService
from frontend.styles import render_kpi_card

lyria_service = LyriaSynthService()
aoi_synth_service = NanoBananaAOIService()

SCENARIO_CARDS = [
    {
        "id": "CHATTER_4210HZ",
        "title": "⚡ Chatter 4210 Hz",
        "subtitle": "Tool T03 Flank Wear Harmonic",
        "ae_sig": "Ch 0 AE: 2.84 G (4.21 kHz peak)",
        "ct_sig": "Ch 1 CT: 0.46 A (68.5 Hz sideband)",
        "expected": "YELLOW_M01_HOLD",
        "accent": "amber",
    },
    {
        "id": "WRENCH_STRIKE",
        "title": "🔨 Wrench Strike False-Positive",
        "subtitle": "90 dB Table Shock Immunity",
        "ae_sig": "Ch 0 AE: Sharp Impulse Spike",
        "ct_sig": "Ch 1 CT: < 0.12 A (Flat Load)",
        "expected": "GREEN_FALSE_POSITIVE_REJECTED",
        "accent": "emerald",
    },
    {
        "id": "BEARING_SPALLING",
        "title": "⚙️ Bearing Spall (184 Hz)",
        "subtitle": "Spindle Outer-Race BPFO Defect",
        "ae_sig": "Ch 0 AE: 184 Hz Periodic Train",
        "ct_sig": "Ch 1 CT: 0.31 A Coupled Ripple",
        "expected": "YELLOW_M01_HOLD",
        "accent": "amber",
    },
    {
        "id": "NOMINAL_CUT",
        "title": "🟢 Nominal Cut",
        "subtitle": "ISO 10816 Golden Baseline",
        "ae_sig": "Ch 0 AE: 0.92 G Broadband Floor",
        "ct_sig": "Ch 1 CT: 0.18 A Smooth 50 Hz",
        "expected": "GREEN_NOMINAL",
        "accent": "emerald",
    },
]


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


def _evaluate_injected_wav_stage_a(wav_bytes: bytes) -> tuple[dict[str, Any], np.ndarray]:
    fs, data = wavfile.read(io.BytesIO(wav_bytes))
    if data.dtype == np.int16:
        data = (data / 32768.0).astype(np.float32)
    else:
        data = data.astype(np.float32)
    start_idx = 24000 if len(data) >= 36000 else 0
    chunk = data[start_idx : start_idx + 12000, :]
    relay = HardwareRelayController()
    q = mp.Queue()
    res = stage_a_deterministic_fast_path(chunk, relay, q, {"tool_id": "T03", "pass_type": "FINISHING"})
    return res, chunk


def _render_dual_channel_oscilloscope_png(chunk_250ms: np.ndarray, stem_id: str, dsp_res: dict[str, Any]) -> bytes:
    """Renders a high-contrast Industrial Dark Slate dual-channel oscilloscope PNG (Ch 0 Piezo AE vs Ch 1 Split-Core CT)."""
    w, h = 760, 250
    img = Image.new("RGB", (w, h), color=(11, 17, 32))
    draw = ImageDraw.Draw(img)

    # Subtle oscilloscope graticule grid
    for gx in range(40, w - 20, 70):
        draw.line((gx, 28, gx, h - 16), fill=(24, 34, 52), width=1)
    for gy in (75, 125, 185):
        draw.line((40, gy, w - 20, gy), fill=(28, 40, 62), width=1)

    # Extract 25 ms zoom window (1200 samples @ 48 kHz) around peak activity so carrier & impulse are clearly visible
    ch0_g = chunk_250ms[:, 0] * VIBRATION_G_PER_FS
    ch1_a = chunk_250ms[:, 1] * CT_AMPS_PER_FS
    peak_center = int(np.argmax(np.abs(ch0_g)))
    win_half = 600
    s0 = max(0, min(len(ch0_g) - 1200, peak_center - win_half))
    seg0 = ch0_g[s0 : s0 + 1200]
    seg1 = ch1_a[s0 : s0 + 1200]

    plot_w = w - 60
    xs = np.linspace(40, w - 20, num=320).astype(int)
    idx = np.linspace(0, len(seg0) - 1, num=320).astype(int)

    # Top trace: Ch 0 Contact Piezo AE (Cyan/Amber)
    max0 = max(float(np.max(np.abs(seg0))), 1.5)
    y0_center = 78
    pts0 = [(int(x), int(y0_center - (seg0[i] / max0) * 38)) for x, i in zip(xs, idx)]
    trace0_color = (245, 158, 11) if "YELLOW" in dsp_res.get("stage_a_state", "") else (56, 189, 248)
    draw.line(pts0, fill=trace0_color, width=2)

    # Bottom trace: Ch 1 Split-Core CT Current (Emerald)
    max1 = max(float(np.max(np.abs(seg1))), 0.6)
    y1_center = 186
    pts1 = [(int(x), int(y1_center - (seg1[i] / max1) * 38)) for x, i in zip(xs, idx)]
    draw.line(pts1, fill=(16, 185, 129), width=2)

    # Frame & Channel HUD Labels
    draw.rectangle((0, 0, w - 1, 26), fill=(17, 24, 39))
    draw.text(
        (12, 6),
        f"48 kHz DUAL-CHANNEL OSCILLOSCOPE  |  STEM: {stem_id}  |  STAGE A: {dsp_res.get('latency_ms', 1.12):.2f} ms",
        fill=(248, 250, 252),
    )
    draw.text(
        (46, 32),
        f"CH 0: Contact Piezo AE (2-8 kHz) • RMS: {dsp_res.get('ae_rms_g', 0.0):.2f} G • Ratio: {dsp_res.get('band_power_ratio_2k_8k', 0.0):.2f}",
        fill=trace0_color,
    )
    draw.text(
        (46, 136),
        f"CH 1: Split-Core Motor CT (50-400 Hz) • Ripple Std: {dsp_res.get('ct_ripple_std_amps', 0.0):.3f} A (Gate >= 0.120 A)",
        fill=(52, 211, 153),
    )
    draw.rectangle((0, 0, w - 1, h - 1), outline=(51, 65, 85), width=2)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


@st.fragment
def render_lyria_studio_view(backend_url: str = "http://localhost:8000"):
    """Renders the Fault Calibration & Demo Studio with 4 tactile scenario cards & dual-channel oscilloscope."""
    tab_acoustic, tab_visual = st.tabs(
        [
            "🎚️ Stereo 48 kHz Fault Scenario Studio & Dual-Channel Oscilloscope",
            "🧪 Nano Banana Pro Day-0 Synthetic Defect Calibration",
        ]
    )

    with tab_acoustic:
        if "selected_fault_stem" not in st.session_state:
            st.session_state["selected_fault_stem"] = "CHATTER_4210HZ"

        st.markdown(
            """
            <div class="hmi-panel" style="margin-bottom: 10px;">
                <div class="hmi-section-header">
                    <span class="hmi-section-title">1. Tactile 48 kHz Fault Scenario Trigger Cards (Day-1 Calibration &amp; Judge Torture Test)</span>
                    <span class="hmi-pill-tag">Lyria Stereo 48 kHz Stems</span>
                </div>
                <div style="font-size: 0.78rem; color: #94A3B8;">
                    Click any scenario trigger card below to inject a calibrated stereo 48 kHz waveform directly into <code>stage_a_deterministic_fast_path()</code>.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 4 Tactile Scenario Trigger Cards
        cols = st.columns(4, gap="small")
        for idx, card in enumerate(SCENARIO_CARDS):
            is_active = st.session_state["selected_fault_stem"] == card["id"]
            active_cls = f"active-{card['accent']}" if is_active else ""
            status_tag = "● ACTIVE STEM" if is_active else "READY"
            tag_color = "#F59E0B" if card["accent"] == "amber" else "#10B981"

            with cols[idx]:
                st.markdown(
                    f"""
                    <div class="scenario-card {active_cls}">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                            <span style="font-family:'JetBrains Mono',monospace; font-size:0.68rem; font-weight:800; color:{tag_color};">{status_tag}</span>
                            <span style="font-family:'JetBrains Mono',monospace; font-size:0.66rem; color:#94A3B8;">48 kHz</span>
                        </div>
                        <div style="font-size:0.92rem; font-weight:800; color:#F8FAFC; margin-bottom:2px;">{card['title']}</div>
                        <div style="font-size:0.74rem; color:#94A3B8; margin-bottom:6px;">{card['subtitle']}</div>
                        <div style="background:#0B1120; border:1px solid #1E293B; border-radius:5px; padding:6px 8px; font-family:'JetBrains Mono',monospace; font-size:0.69rem; color:#CBD5E1; line-height:1.45;">
                            <div>{card['ae_sig']}</div>
                            <div>{card['ct_sig']}</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(
                    f"Inject {card['title'].split(' ', 1)[1]}",
                    key=f"trigger_card_{card['id']}",
                    type="primary" if is_active else "secondary",
                    use_container_width=True,
                ):
                    st.session_state["selected_fault_stem"] = card["id"]
                    st.rerun()

        stem_type = st.session_state["selected_fault_stem"]
        wav_bytes, meta = _synthesize_or_fallback(backend_url, stem_type)
        dsp_live, chunk_250ms = _evaluate_injected_wav_stage_a(wav_bytes)

        state_val = dsp_live.get("stage_a_state", "YELLOW_M01_HOLD")
        exec_ms = max(float(dsp_live.get("latency_ms", 1.12)), 0.15)
        band_ratio = dsp_live.get("band_power_ratio_2k_8k", 0.71)
        coh_val = dsp_live.get("coherence", 0.84)
        ct_std = dsp_live.get("ct_ripple_std_amps", 0.46)

        state_accent = "amber" if "YELLOW" in state_val else ("red" if "RED" in state_val else "emerald")

        # Un-truncated Stage Latency & Telemetry KPI Cards (Replaces truncated st.metric)
        studio_kpis = (
            '<div class="kpi-strip-grid" style="margin-top: 8px;">'
            + render_kpi_card(
                label="Triggered Edge State",
                value=state_val,
                subtitle=f"Source: {dsp_live.get('detection_source', 'NOMINAL')}",
                accent=state_accent,
                sub_color=state_accent,
            )
            + render_kpi_card(
                label="Stage A DSP Latency",
                value=f"Stage A DSP: {exec_ms:.2f} ms",
                subtitle="Deterministic < 1.40 ms Budget",
                accent="cyan",
                sub_color="cyan",
            )
            + render_kpi_card(
                label="Ch 0 2–8 kHz Band Power",
                value=f"{band_ratio:.2f} | {dsp_live.get('ae_rms_g', 0.0):.2f} G",
                subtitle=f"Crest Factor: {dsp_live.get('spectral_crest_factor', 0.0):.1f}",
                accent="amber",
                sub_color="amber",
            )
            + render_kpi_card(
                label="Envelope Coherence & CT",
                value=f"Coh: {coh_val:.2f} | {ct_std:.3f} A",
                subtitle="Wrench Gate Floor: 0.120 A",
                accent="emerald",
                sub_color="emerald",
            )
            + "</div>"
        )
        st.markdown(studio_kpis, unsafe_allow_html=True)

        # Real-time Dual-Channel Oscilloscope Preview + Stereo Audio Player
        col_scope, col_audio = st.columns([1.45, 1.0], gap="large")
        with col_scope:
            scope_png = _render_dual_channel_oscilloscope_png(chunk_250ms, stem_type, dsp_live)
            st.image(
                scope_png,
                caption="Real-Time Dual-Channel Oscilloscope Preview (Ch 0 Contact Piezo AE vs Ch 1 Split-Core Motor CT)",
                use_container_width=True,
            )

        with col_audio:
            st.markdown(
                f"""
                <div class="hmi-panel">
                    <div class="hmi-section-header">
                        <span class="hmi-section-title">🎧 Stereo 48 kHz Stem Playback</span>
                        <span class="hmi-pill-tag amber">{stem_type}</span>
                    </div>
                    <div style="font-size: 0.8rem; color: #E2E8F0; line-height: 1.5; margin-bottom: 8px;">
                        {meta.get("description", "Calibrated stereo 48 kHz synthetic fault stem layered over Pune-Chakan shop-floor ambient hum.")}
                    </div>
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.73rem; color: #94A3B8; margin-bottom: 6px;">
                        Left (Ch 0): Piezo Structure-Borne AE &bull; Right (Ch 1): Clamped CT
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.audio(wav_bytes, format="audio/wav")

    with tab_visual:
        st.markdown(
            f"""
            <div class="hmi-panel">
                <div class="hmi-section-header">
                    <span class="hmi-section-title">Day-0 Synthetic Defect Calibration from Golden Master (REF-01)</span>
                    <span class="hmi-pill-tag amber">{settings.GEMINI_IMAGE_MODEL_ID}</span>
                </div>
                <div style="font-size: 0.8rem; color: #94A3B8;">
                    Synthesizes physically grounded cross-polarized surface defects on Day 0 so new factories can bootstrap visual QA before scrapping a single casting.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        defect_choice = st.selectbox(
            "Select Target Synthetic Defect Class:",
            ["MICRO_BURR_REJECT", "CHATTER_SCAR_REJECT", "FOUNDRY_POROSITY_CHARGEBACK"],
            index=0,
        )
        if st.button("✨ SYNTHESIZE DAY-0 DEFECT EXEMPLAR (NANO BANANA PRO)", type="primary"):
            golden_path = Path("data/golden_references/REF-01.jpg")
            if golden_path.exists():
                synth_bytes = None
                candidates = [backend_url.rstrip("/")]
                if settings.BACKEND_API_URL.rstrip("/") not in candidates:
                    candidates.append(settings.BACKEND_API_URL.rstrip("/"))
                for target_url in candidates:
                    try:
                        with httpx.Client(timeout=4.0) as client:
                            resp = client.post(
                                f"{target_url}/api/v1/faults/synthesize-defect",
                                json={"defect_type": defect_choice, "base_token_id": "REF-01"},
                            )
                            if resp.status_code == 200:
                                synth_bytes = base64.b64decode(resp.json()["image_b64"])
                                break
                    except Exception:
                        continue
                if synth_bytes is None:
                    synth_bytes = asyncio.run(
                        aoi_synth_service.synthesize_cold_start_defect(
                            base_golden_jpeg_bytes=golden_path.read_bytes(),
                            defect_type=defect_choice,
                        )
                    )
                g_col, s_col = st.columns(2)
                g_col.image(str(golden_path), caption="Golden Master Input (REF-01)", use_container_width=True)
                s_col.image(
                    synth_bytes,
                    caption=f"Nano Banana Pro Synthesized Exemplar ({defect_choice})",
                    use_container_width=True,
                )


def render_fault_injection_studio_view(backend_url: str = "http://localhost:8000"):
    """Backwards-compatible alias delegating to the unified Fault Calibration Studio."""
    render_lyria_studio_view(backend_url=backend_url)
