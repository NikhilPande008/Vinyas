"""
frontend/components/operator_ptt_view.py
ISA-101 High-Performance HMI Operator Screen for Vinyas:
- Distraction-free, 3-second-glanceable CNC Shop-Floor Operator Screen
- Zero model names, zero hardware bindings, zero latency/coherence metrics, zero ROI counters
- Flat neutral dark slate (#0F172A) base; semantic color appears ONLY when human action is required
- 3-Block Layout (Zero scrolling on 1080p):
  * Block 1: Top Machine Status Banner (Full Width, 72px height: VMC-04 • TOOL T03 | Status Pill | Language Pill)
  * Block 2: "What To Do Now" Action Grid (Left 65%: 3 giant 48px bold numbered action cards in M01 HOLD,
    or a single calm grey card in RUNNING state)
  * Block 3: Oversized Fitts's Law Palm-Button Confirmation Zone (Right 35%: min-height 220px tactile
    PRESS & SPEAK button -> instant LISTENING... pulse -> solid Emerald Green ✓ CONFIRMED — PRESS CYCLE START card)
- Preserves @st.fragment isolation and Pydantic bindings (Day1NonInvasiveAction, SanitizedVoiceIntent) under the hood.
"""
import time
from typing import Any
import httpx
import streamlit as st
from backend.models.schemas import Day1NonInvasiveAction, SanitizedVoiceIntent

# Clean vernacular localization table (Zero technical jargon, zero PPAP range clutter)
_LANG_STRINGS: dict[str, dict[str, str]] = {
    "मराठी": {
        "step1_sub": "Feed Knob 85% वर करा",
        "step2_sub": "Speed Knob 90% वर करा",
        "step3_sub": "T03 Insert Corner #2 बदला",
        "palm_sub": 'बटण दाबा आणि बोला: "T03 बदलला"',
        "normal_msg": "Machine Normal — Continue Production.",
        "normal_sub": "मशीन सुरळीत चालू आहे — उत्पादन सुरू ठेवा.",
        "confirmed_sub": "पुढील सायकल सुरू करण्यासाठी हिरवे CYCLE START बटण दाबा",
        "default_utterance": "T03 corner 2 badalala, resume kara",
    },
    "हिंदी": {
        "step1_sub": "Feed Knob 85% पर करें",
        "step2_sub": "Speed Knob 90% पर करें",
        "step3_sub": "T03 Insert Corner #2 बदलें",
        "palm_sub": 'बटन दबाएं और बोलें: "T03 बदला"',
        "normal_msg": "Machine Normal — Continue Production.",
        "normal_sub": "मशीन सामान्य है — उत्पादन जारी रखें।",
        "confirmed_sub": "अगली साइकिल शुरू करने के लिए हरा CYCLE START बटन दबाएं",
        "default_utterance": "T03 corner 2 badal diya, resume karo",
    },
    "EN": {
        "step1_sub": "Set Feed Knob to 85%",
        "step2_sub": "Set Speed Knob to 90%",
        "step3_sub": "Index T03 Insert to Corner #2",
        "palm_sub": 'Press button & say: "T03 swapped"',
        "normal_msg": "Machine Normal — Continue Production.",
        "normal_sub": "All cutting parameters nominal — no operator action required.",
        "confirmed_sub": "Action logged. Press physical green CYCLE START on controller.",
        "default_utterance": "T03 insert corner 2 swapped, resume cycle",
    },
}


def _build_bound_day1_action(lang: str) -> Day1NonInvasiveAction:
    """Maintains strict Pydantic Day1NonInvasiveAction contract under the hood."""
    strings = _LANG_STRINGS.get(lang, _LANG_STRINGS["मराठी"])
    return Day1NonInvasiveAction(
        operator_feedrate_dial_pct=85,
        spindle_speed_dial_pct=90,
        m01_manual_wear_offset_z_microns=12.0,
        require_insert_indexing=True,
        operator_card_marathi=(
            f"1: {strings['step1_sub']} | 2: {strings['step2_sub']} | 3: {strings['step3_sub']}"
        ),
    )


def _send_voice_utterance(backend_url: str, utterance: str) -> SanitizedVoiceIntent:
    """Calls backend voice gate and returns a validated SanitizedVoiceIntent Pydantic model."""
    try:
        with httpx.Client(timeout=2.5) as client:
            resp = client.post(
                f"{backend_url}/api/v1/voice/interact",
                json={
                    "utterance": utterance,
                    "machine_state": "YELLOW_M01_HOLD",
                    "context": {
                        "event_id": "evt_chakan_vmc04_99281",
                        "machine_id": "FANUC_0iTF_CHAKAN_04",
                        "tool_id": "T03",
                        "estimated_savings_inr": 16200,
                        "cycle_time_penalty_sec": 4.2,
                    },
                },
            )
            if resp.status_code == 200:
                return SanitizedVoiceIntent.model_validate(resp.json())
    except Exception:
        pass

    lower = utterance.lower()
    if "supervisor" in lower or "bolva" in lower:
        return SanitizedVoiceIntent(
            intent="REQUEST_SUPERVISOR",
            spoken_response_marathi="Supervisor la alert pathavla aahe.",
            served_from_fallback=True,
        )
    if "ka thambla" in lower or "explain" in lower:
        return SanitizedVoiceIntent(
            intent="EXPLAIN_HOLD",
            spoken_response_marathi="Feed 85% kara ani T03 Corner 2 insert firva.",
            served_from_fallback=True,
        )
    if "hammer" in lower or "normal" in lower:
        return SanitizedVoiceIntent(
            intent="IGNORE_NOISE",
            spoken_response_marathi="Cut normal aahe.",
            served_from_fallback=True,
        )
    return SanitizedVoiceIntent(
        intent="CONFIRM_INSERT_SWAP",
        spoken_response_marathi="धन्यवाद! T03 Corner #2 आणि 85% Feed confirm झाले आहे.",
        served_from_fallback=True,
    )


def _render_language_pill_html(active_lang: str) -> str:
    parts = []
    for lang in ("मराठी", "हिंदी", "EN"):
        if lang == active_lang:
            parts.append(f'<span class="isa101-lang-active">{lang}</span>')
        else:
            parts.append(f"<span>{lang}</span>")
    joined = ' <span style="color:#475569;">|</span> '.join(parts)
    return f'<div class="isa101-lang-pill">{joined}</div>'


@st.fragment
def render_operator_ptt_view(backend_url: str = "http://localhost:8000"):
    """Renders the ISA-101 High-Performance HMI 3-Block CNC Operator Screen."""
    # Collapse sidebar and enforce flat #0F172A ISA-101 slate background on Operator View
    st.markdown(
        """
        <style>
        html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
            background-color: #0F172A !important;
        }
        [data-testid="stSidebar"] {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if "op_lang" not in st.session_state:
        st.session_state["op_lang"] = "मराठी"
    if "op_machine_state" not in st.session_state:
        st.session_state["op_machine_state"] = "M01_HOLD"
    if "op_ptt_confirmed" not in st.session_state:
        st.session_state["op_ptt_confirmed"] = False

    active_lang: str = st.session_state["op_lang"]
    machine_state: str = st.session_state["op_machine_state"]
    ptt_confirmed: bool = st.session_state["op_ptt_confirmed"]

    # Bind Pydantic contract under the hood
    day1_action = _build_bound_day1_action(active_lang)
    strings = _LANG_STRINGS[active_lang]

    # Discrete Switch Role button in top-left corner (sidebar is hidden by default on Operator View)
    top_nav_col, _spacer = st.columns([0.16, 0.84])
    with top_nav_col:
        if st.button("← Switch Role", key="op_top_left_switch_role_btn"):
            st.session_state["active_station_nav"] = "1. Supervisor Cockpit"
            st.rerun()

    # =========================================================================
    # BLOCK 1: Top Machine Status Banner (Full Width, 72px height)
    # =========================================================================
    if machine_state == "RUNNING":
        status_pill_html = '<div class="isa101-status-pill-normal">RUNNING — NO ACTION NEEDED</div>'
    elif machine_state == "EMERGENCY_STOP":
        status_pill_html = '<div class="isa101-status-pill-stop">🛑 EMERGENCY STOP</div>'
    else:
        status_pill_html = '<div class="isa101-status-pill-hold">⚠ M01 HOLD — ACTION REQUIRED</div>'

    lang_pill_html = _render_language_pill_html(active_lang)

    st.markdown(
        f"""
        <div class="isa101-top-banner">
            <div class="isa101-machine-id">VMC-04 &bull; TOOL T03</div>
            <div>{status_pill_html}</div>
            <div>{lang_pill_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # =========================================================================
    # BLOCK 2 (Left 65%) & BLOCK 3 (Right 35%): Zero-Scroll Main Canvas
    # =========================================================================
    col_actions, col_palm = st.columns([1.85, 1.0], gap="large")

    with col_actions:
        if machine_state == "RUNNING":
            st.markdown(
                f"""
                <div class="isa101-normal-calm-card">
                    <div style="font-size: 2.1rem; font-weight: 800; color: #94A3B8; letter-spacing: -0.01em;">
                        {strings['normal_msg']}
                    </div>
                    <div style="font-size: 1.25rem; font-weight: 600; color: #64748B; margin-top: 10px;">
                        {strings['normal_sub']}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div class="isa101-action-grid">
                    <!-- STEP 1: DIAL FEED -->
                    <div class="isa101-action-card">
                        <div class="isa101-step-header">1. STEP 1 — DIAL FEED</div>
                        <div class="isa101-giant-value">{day1_action.operator_feedrate_dial_pct}%</div>
                        <div class="isa101-sub-label">{strings['step1_sub']}</div>
                    </div>

                    <!-- STEP 2: DIAL SPEED -->
                    <div class="isa101-action-card">
                        <div class="isa101-step-header">2. STEP 2 — DIAL SPEED</div>
                        <div class="isa101-giant-value">{day1_action.spindle_speed_dial_pct}%</div>
                        <div class="isa101-sub-label">{strings['step2_sub']}</div>
                    </div>

                    <!-- STEP 3: TOOL T03 -->
                    <div class="isa101-action-card">
                        <div class="isa101-step-header">3. STEP 3 — TOOL T03</div>
                        <div class="isa101-giant-value">CORNER #2</div>
                        <div class="isa101-sub-label">{strings['step3_sub']}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col_palm:
        feedback_slot = st.empty()

        if not ptt_confirmed:
            with feedback_slot.container():
                st.markdown('<div class="isa101-palm-scope">', unsafe_allow_html=True)
                palm_pressed = st.button(
                    f"🎙️🤚 PRESS & SPEAK\n{strings['palm_sub']}",
                    key="isa101_palm_ptt_btn",
                    type="primary",
                    use_container_width=True,
                )
                st.markdown("</div>", unsafe_allow_html=True)

            if palm_pressed:
                # 1. Instant pulsing LISTENING... state for input certainty
                feedback_slot.markdown(
                    """
                    <div class="isa101-listening-card">
                        <div style="font-size: 2.4rem; margin-bottom: 6px;">🎙️</div>
                        <div style="font-size: 1.75rem; font-weight: 900; color: #0F172A; letter-spacing: 0.04em;">
                            LISTENING...
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                utterance = st.session_state.get("demo_custom_utterance", strings["default_utterance"])
                validated_intent = _send_voice_utterance(backend_url, utterance)
                st.session_state["last_sanitized_voice_intent"] = validated_intent.model_dump()
                time.sleep(0.35)
                st.session_state["op_ptt_confirmed"] = True
                # 2. Immediately flip to solid Emerald Green confirmation card
                feedback_slot.markdown(
                    f"""
                    <div class="isa101-confirmed-card">
                        <div class="isa101-confirmed-title">✓ CONFIRMED — PRESS CYCLE START</div>
                        <div class="isa101-confirmed-sub">{strings['confirmed_sub']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            # 2. Solid Emerald Green confirmation card
            feedback_slot.markdown(
                f"""
                <div class="isa101-confirmed-card">
                    <div class="isa101-confirmed-title">✓ CONFIRMED — PRESS CYCLE START</div>
                    <div class="isa101-confirmed-sub">{strings['confirmed_sub']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # =========================================================================
    # DISCRETE DEMO CONTROLS EXPANDER (Collapsed at Very Bottom of Page)
    # =========================================================================
    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
    with st.expander("Demo Controls", expanded=False):
        d_col1, d_col2, d_col3, d_col4 = st.columns([1.0, 1.0, 1.6, 0.8])

        with d_col1:
            st.radio(
                "Operator Language",
                ["मराठी", "हिंदी", "EN"],
                key="op_lang",
                horizontal=True,
            )

        with d_col2:
            st.selectbox(
                "Simulated Machine State",
                ["M01_HOLD", "RUNNING", "EMERGENCY_STOP"],
                key="op_machine_state",
            )

        with d_col3:
            preset_utterance = st.selectbox(
                "Demo Voice Preset",
                [
                    "T03 corner 2 badalala, resume kara",
                    "Machine ka thambla? Tool badlaycha ka?",
                    "Supervisor la bolva, bore size check karaycha aahe",
                    "Floor var hammer padla, cut normal aahe",
                ],
                index=0,
            )
            st.session_state["demo_custom_utterance"] = preset_utterance

        with d_col4:
            if st.button("Reset PTT State", use_container_width=True):
                st.session_state["op_ptt_confirmed"] = False
            if st.button("Switch Role", use_container_width=True):
                st.session_state["active_station_nav"] = "1. Supervisor Cockpit"
                st.rerun()
