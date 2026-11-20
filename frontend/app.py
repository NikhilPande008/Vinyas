"""
frontend/app.py
Vinyas (NadaTwin V2.1): Unified Pure Streamlit >= 1.40 Entrypoint (Team Vinyas — Nikhil Pande & Ravi Mule).
- Industrial Dark Slate HMI Theme (#0B1120 canvas, #111827 cards, zero glare under overhead shop-floor LEDs)
- Every persona view isolated via @st.fragment so Gemini Live WebSocket audio never drops on rerun
- Single-line 56px sticky status header consolidating brand, Stage A DSP telemetry, Relay badge, and 1-click LIVE/SAFE pill
- Streamlined Left Navigation Rail with 4 clear station buttons + collapsible Hardware & Model Binding drawer
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
import streamlit as st
from config.settings import settings
from frontend.styles import inject_industrial_hmi_css
from frontend.components.supervisor_cockpit import render_supervisor_cockpit
from frontend.components.operator_ptt_view import render_operator_ptt_view
from frontend.components.qa_inspector_view import render_qa_inspector_view
from frontend.components.lyria_studio_view import render_lyria_studio_view

st.set_page_config(
    page_title="Vinyas (NadaTwin V2.1) | Industrial CNC Acoustic & Optical HMI",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

BACKEND_URL = settings.resolve_backend_url()
FALLBACK_LOCAL_BACKEND_URL = settings.BACKEND_API_URL


def _post_with_backend_failover(path: str, json_payload: dict | None = None, timeout: float = 2.0):
    candidates = [BACKEND_URL]
    if FALLBACK_LOCAL_BACKEND_URL not in candidates:
        candidates.append(FALLBACK_LOCAL_BACKEND_URL)
    for base in candidates:
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(f"{base}{path}", json=json_payload)
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            continue
    return None


def _toggle_circuit_breaker() -> bool:
    data = _post_with_backend_failover("/api/v1/demo/toggle-safe-mode")
    if data is not None:
        settings.DEMO_SAFE_MODE = data.get("demo_safe_mode", True)
        st.session_state["served_from_fallback"] = settings.DEMO_SAFE_MODE
        return settings.DEMO_SAFE_MODE
    settings.DEMO_SAFE_MODE = not settings.DEMO_SAFE_MODE
    st.session_state["served_from_fallback"] = settings.DEMO_SAFE_MODE
    return settings.DEMO_SAFE_MODE


def _toggle_relay_mode() -> str:
    data = _post_with_backend_failover("/api/v1/relay/toggle-mode")
    if data is not None:
        settings.RELAY_OPERATING_MODE = data.get("relay_operating_mode", "DAY1_ANDON_ONLY")
        return settings.RELAY_OPERATING_MODE
    settings.RELAY_OPERATING_MODE = (
        "DAY30_EXT_FEED_HOLD_CUTOUT"
        if settings.RELAY_OPERATING_MODE == "DAY1_ANDON_ONLY"
        else "DAY1_ANDON_ONLY"
    )
    return settings.RELAY_OPERATING_MODE


def _fetch_header_routing_metrics() -> tuple[int, int]:
    candidates = [BACKEND_URL]
    if FALLBACK_LOCAL_BACKEND_URL not in candidates:
        candidates.append(FALLBACK_LOCAL_BACKEND_URL)
    for base in candidates:
        try:
            with httpx.Client(timeout=1.5) as client:
                resp = client.get(f"{base}/api/v1/telemetry/shift-aggregates")
                if resp.status_code == 200:
                    data = resp.json()
                    return int(data.get("edge_suppressed_pct", 88)), int(data.get("cloud_escalated_pct", 12))
        except Exception:
            continue
    return 88, 12


@st.fragment
def render_header_status_bar():
    """Single-line 56px sticky top status bar with live telemetry routing counter, relay badge, and circuit-breaker pill."""
    h_col1, h_col2, h_col3, h_col4 = st.columns([1.25, 2.35, 0.70, 0.70], vertical_alignment="center")

    edge_pct, cloud_pct = _fetch_header_routing_metrics()
    relay_short = "DAY1 ANDON" if settings.RELAY_OPERATING_MODE == "DAY1_ANDON_ONLY" else "DAY30 CUTOUT"
    served_from_fallback = bool(st.session_state.get("served_from_fallback", settings.DEMO_SAFE_MODE))
    is_fallback_mode = settings.DEMO_SAFE_MODE or served_from_fallback
    mode_label = "FALLBACK" if is_fallback_mode else "LIVE"
    mode_color = "#F59E0B" if is_fallback_mode else "#10B981"

    with h_col1:
        st.markdown(
            """
            <div class="vinyas-brand-cluster" style="min-height: 48px;">
                <span style="font-size: 1.55rem; line-height: 1;">🏭</span>
                <div>
                    <div class="vinyas-brand-title">Vinyas <span style="color: #F59E0B; font-size: 0.82rem; font-weight: 700;">NadaTwin V2.1</span></div>
                    <div class="vinyas-brand-subtitle">Pune-Chakan • Cloud Run (asia-south1)</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with h_col2:
        st.markdown(
            f"""
            <div class="vinyas-telemetry-pill">
                <span class="telemetry-dot"></span>
                <span>Edge Suppressed (Nominal): <strong style="color:#10B981;">{edge_pct}%</strong></span>
                <span style="color:#475569;">|</span>
                <span>Escalated to Cloud Run: <strong style="color:#38BDF8;">{cloud_pct}%</strong></span>
                <span style="color:#475569;">|</span>
                <span>Mode: <strong style="color:{mode_color};">{mode_label}</strong></span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with h_col3:
        if st.button(f"🔌 {relay_short}", key="toggle_relay_mode_btn", use_container_width=True):
            _toggle_relay_mode()
            st.rerun()

    with h_col4:
        btn_type = "secondary" if is_fallback_mode else "primary"
        if st.button(f"🛡️ Mode: {mode_label}", key="toggle_safe_mode_btn", type=btn_type, use_container_width=True):
            _toggle_circuit_breaker()
            st.rerun()


def main():
    inject_industrial_hmi_css()

    if "active_station_nav" not in st.session_state:
        st.session_state["active_station_nav"] = "1. Supervisor Cockpit"

    st.sidebar.markdown(
        """
        <div style="padding: 4px 2px 10px 2px; border-bottom: 1px solid #1E293B; margin-bottom: 10px;">
            <div style="font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #94A3B8;">
                SHOP-FLOOR STATION SELECTOR
            </div>
            <div style="font-size: 0.95rem; font-weight: 800; color: #F8FAFC; margin-top: 2px;">
                Vinyas HMI Stations
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    view_choice = st.sidebar.radio(
        "Station Navigation",
        [
            "1. Supervisor Cockpit",
            "2. Operator Voice Pod",
            "3. Optical QA & Provenance",
            "4. Fault Calibration Studio",
        ],
        key="active_station_nav",
        label_visibility="collapsed",
    )

    st.sidebar.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

    with st.sidebar.expander("⚙️ Hardware & Model Binding", expanded=False):
        st.markdown(
            f"""
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.74rem; color: #CBD5E1; line-height: 1.65;">
                <div><span style="color:#94A3B8;">Cloud Run  :</span> <strong style="color:#38BDF8;">{BACKEND_URL}</strong></div>
                <div><span style="color:#94A3B8;">ADC Source :</span> <strong style="color:#38BDF8;">{settings.HARDWARE_SOURCE}</strong></div>
                <div><span style="color:#94A3B8;">Relay Mode :</span> <strong style="color:#F59E0B;">{settings.RELAY_OPERATING_MODE}</strong></div>
                <div><span style="color:#94A3B8;">V-Block Cam:</span> <strong>Idx {settings.CAMERA_DEVICE_INDEX}</strong></div>
                <div><span style="color:#94A3B8;">Circuit Brk:</span> <strong style="color:#10B981;">{"FALLBACK_CACHE" if (settings.DEMO_SAFE_MODE or st.session_state.get("served_from_fallback", False)) else "LIVE_CLOUD_RUN"}</strong></div>
                <div><span style="color:#94A3B8;">BQ Dataset :</span> <code>{settings.BQ_DATASET}</code></div>
                <hr style="margin: 6px 0; border-color: #1E293B;"/>
                <div><span style="color:#94A3B8;">Omni Cloud :</span> <code>{settings.GEMINI_OMNI_MODEL_ID}</code></div>
                <div><span style="color:#94A3B8;">Edge Gate  :</span> <code>{settings.EDGE_GEMMA_MODEL_ID}</code></div>
                <div><span style="color:#94A3B8;">Marathi Op :</span> <code>{settings.VERNACULAR_GEMMA_MODEL_ID}</code></div>
                <div><span style="color:#94A3B8;">Voice PTT  :</span> <code>{settings.GEMINI_LIVE_MODEL_ID}</code></div>
                <div><span style="color:#94A3B8;">Day-0 Synth:</span> <code>{settings.GEMINI_IMAGE_MODEL_ID}</code></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.sidebar.markdown(
        """
        <div style="margin-top: 16px; padding-top: 10px; border-top: 1px solid #1E293B; font-size: 0.72rem; color: #64748B;">
            <strong>Team Vinyas</strong> • Nikhil Pande &amp; Ravi Mule<br/>
            Physics Calculates, AI Diagnoses
        </div>
        """,
        unsafe_allow_html=True,
    )

    if view_choice.startswith("2."):
        # Operator Screen follows strict ISA-101 zero-jargon rules:
        # no engineering telemetry header, sidebar hidden by default, discrete Switch Role button in top-left.
        render_operator_ptt_view(backend_url=BACKEND_URL)
    else:
        render_header_status_bar()
        st.markdown("<hr style='margin: 4px 0 12px 0; border-color: #1E293B;'/>", unsafe_allow_html=True)
        if view_choice.startswith("1."):
            render_supervisor_cockpit(backend_url=BACKEND_URL)
        elif view_choice.startswith("3."):
            render_qa_inspector_view(backend_url=BACKEND_URL)
        elif view_choice.startswith("4."):
            render_lyria_studio_view(backend_url=BACKEND_URL)


if __name__ == "__main__":
    main()
