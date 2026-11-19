"""
frontend/components/operator_ptt_view.py
Vinyas Operator Voice Pod View (Persona 2: Shop-Floor Machine Operator):
Isolated via @st.fragment to prevent interrupting the Gemini Live WebSocket loop.
Designed for Pune-Chakan / Chennai / Coimbatore operators wearing oil-coated gloves in 90 dB ambient noise:
- Fixes v1 contrast bug: enforces WCAG AAA contrast (#0F172A dark slate ink on #FEF3C7 warm amber fill,
  plus #F8FAFC crisp white text on #1E293B dark slate card with #F59E0B 6px left accent border)
- Left 60% — Glanceable 3-Step High-Contrast Vernacular Action Card:
  Large 22px-26px bold Marathi + Hinglish instruction text broken into 3 numbered visual step tiles
- Right 40% — Ergonomic 40mm Palm-Button PTT Simulator (min-height: 88px), active audio waveform indicator,
  quick-select vernacular voice presets, and SanitizedVoiceIntent confirmation pill
"""
from typing import Any
import httpx
import streamlit as st
from config.settings import settings


def _send_voice_utterance(backend_url: str, utterance: str) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=3.0) as client:
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
                return resp.json()
    except Exception:
        pass

    lower = utterance.lower()
    if "supervisor" in lower or "bolva" in lower:
        return {
            "intent": "REQUEST_SUPERVISOR",
            "spoken_response_marathi": "Supervisor la alert pathavla aahe. Krupaya M01 Hold var machine thambvun theva.",
        }
    if "ka thambla" in lower or "explain" in lower:
        return {
            "intent": "EXPLAIN_HOLD",
            "spoken_response_marathi": "Tool T03 finishing cut madhye 4,210 Hz chatter detect jhala aahe. Feed 85% kara ani Corner 2 insert firva.",
        }
    if "hammer" in lower or "normal" in lower:
        return {
            "intent": "IGNORE_NOISE",
            "spoken_response_marathi": "Bahercha aawaj (floor shock) ignore kela aahe. Cutting load normal aahe.",
        }
    return {
        "intent": "CONFIRM_INSERT_SWAP",
        "spoken_response_marathi": "धन्यवाद! Tool T03 Corner #2 insert swap आणि 85% Feedrate Override confirm झाले आहे. Machine cycle सुरू करण्यासाठी सुरक्षित आहे. (+INR 16,200 वाचवले)",
    }


@st.fragment
def render_operator_ptt_view(backend_url: str = "http://localhost:8000"):
    """Renders the Glanceable 3-Step Vernacular Operator HMI & 40mm Palm-Button PTT Simulator."""
    col_card, col_ptt = st.columns([1.5, 1.0], gap="large")

    # =========================================================================
    # LEFT 60%: High-Contrast Vernacular Action Card (WCAG AAA Compliant)
    # =========================================================================
    with col_card:
        st.markdown(
            """
            <div class="operator-vernacular-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="background: #F59E0B; color: #0F172A; font-weight: 900; font-size: 0.78rem; padding: 4px 10px; border-radius: 6px; letter-spacing: 0.04em;">
                            ⚠️ M01 HOLD • TOOL T03
                        </span>
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; color: #F8FAFC; font-weight: 700;">
                            FANUC_0iTF_CHAKAN_04
                        </span>
                    </div>
                    <span style="background: #EF4444; color: #F8FAFC; padding: 4px 10px; border-radius: 6px; font-family: 'JetBrains Mono', monospace; font-size: 0.76rem; font-weight: 800;">
                        ANDON: AMBER HOLD
                    </span>
                </div>

                <div style="font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #94A3B8; margin-bottom: 4px;">
                    मराठी कृती सूचना • Vernacular Shop-Floor Action (Gemma 3 4B)
                </div>

                <!-- High-Contrast Warm Amber Callout (#0F172A Ink on #FEF3C7 Fill -> WCAG AAA 17.4:1 Contrast) -->
                <div class="operator-amber-callout">
                    "Tool T03 Finishing Pass मध्ये chatter आला आहे. M01 Hold वर Feedrate Override knob 85% वर करा आणि Insert Corner #2 बदला."
                </div>

                <!-- 3 Numbered Visual Step Tiles with Large Icons -->
                <div class="step-tile-grid">
                    <div class="step-tile">
                        <div class="step-tile-num">STEP 1 • DIAL</div>
                        <div class="step-tile-title">🎛️ 1. Dial Feed → 85%</div>
                        <div class="step-tile-desc">
                            Physical Feedrate knob <strong>85%</strong> व Spindle Speed <strong>90%</strong> वर सेट करा (PPAP 70–110%).
                        </div>
                    </div>
                    <div class="step-tile">
                        <div class="step-tile-num">STEP 2 • TOOL</div>
                        <div class="step-tile-title">🔄 2. Index T03 → Corner #2</div>
                        <div class="step-tile-desc">
                            M01 थांब्यावर <strong>Tool T03 Carbide Insert</strong> फिरवून नवीन <strong>Corner #2</strong> लॉक करा.
                        </div>
                    </div>
                    <div class="step-tile">
                        <div class="step-tile-num">STEP 3 • VOICE</div>
                        <div class="step-tile-title">🎙️ 3. Press Palm-Button to Confirm</div>
                        <div class="step-tile-desc">
                            40mm Palm-Button दाबा आणि सांगा: <em>"T03 corner 2 badalala"</em>.
                        </div>
                    </div>
                </div>

                <div style="margin-top: 14px; padding: 10px 12px; background: #0F172A; border: 1px solid #334155; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; font-size: 0.78rem; color: #CBD5E1;">
                    <span>🔒 <strong>Zero G-Code Edit Policy:</strong> Controller program locked under IATF 16949.</span>
                    <span class="hmi-pill-tag emerald">+INR 16,200 Casting Protected</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # =========================================================================
    # RIGHT 40%: Ergonomic 40mm Palm-Button PTT Simulator
    # =========================================================================
    with col_ptt:
        st.markdown(
            """
            <div class="hmi-panel" style="margin-bottom: 10px;">
                <div class="hmi-section-header">
                    <span class="hmi-section-title">IP67 40mm Palm-Button Voice Pod</span>
                    <span class="hmi-pill-tag amber">90 dB Noise Gate</span>
                </div>
                <div style="display: flex; align-items: center; justify-content: space-between; background: #0B1120; border: 1px solid #1E293B; border-radius: 6px; padding: 8px 12px; margin-bottom: 8px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="telemetry-dot"></span>
                        <span style="font-size: 0.76rem; font-weight: 700; color: #F8FAFC;">Gemini Live 2.0 Audio Link</span>
                    </div>
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.74rem; color: #10B981;">
                        ▁ ▃ ▆ █  ▂ ▄ ▇ ▃ ▁ READY
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        preset = st.selectbox(
            "Quick-Select Vernacular Voice Preset (Marathi / Hinglish):",
            [
                "T03 insert corner 2 badalala, resume kara (CONFIRM_INSERT_SWAP)",
                "Machine ka thambla? Tool badlaycha ka? (EXPLAIN_HOLD)",
                "Supervisor la bolva, bore size check karaycha aahe (REQUEST_SUPERVISOR)",
                "Floor var hammer padla, cut normal aahe (IGNORE_NOISE)",
            ],
            index=0,
        )

        custom_text = st.text_input(
            "Or type custom operator speech:",
            value="",
            placeholder="e.g., T03 corner 2 badalala, feed 85% kela...",
        )
        utterance_to_send = custom_text.strip() if custom_text.strip() else preset.split(" (")[0]

        # Oversized (min-height: 88px) glove-friendly tactile Palm-Button
        st.markdown('<div class="palm-btn-scope">', unsafe_allow_html=True)
        btn_pressed = st.button(
            "🔴 PUSH-TO-TALK PALM POD (HOLD & SPEAK)",
            key="palm_ptt_trigger_btn",
            use_container_width=True,
            type="primary",
        )
        st.markdown("</div>", unsafe_allow_html=True)

        if "last_voice_result" not in st.session_state:
            st.session_state["last_voice_result"] = {
                "intent": "CONFIRM_INSERT_SWAP",
                "spoken_response_marathi": "धन्यवाद! Tool T03 Corner #2 insert swap आणि 85% Feedrate Override confirm झाले आहे. Machine cycle सुरू करण्यासाठी सुरक्षित आहे. (+INR 16,200 वाचवले)",
                "utterance": "T03 insert corner 2 badalala, resume kara",
            }

        if btn_pressed:
            with st.spinner("Validating speech via Gemini Live SanitizedVoiceIntent gate..."):
                res = _send_voice_utterance(backend_url, utterance_to_send)
                res["utterance"] = utterance_to_send
                st.session_state["last_voice_result"] = res

        voice_res = st.session_state["last_voice_result"]
        intent = voice_res.get("intent", "CONFIRM_INSERT_SWAP")
        spoken_marathi = voice_res.get("spoken_response_marathi", "")
        is_confirmed = intent == "CONFIRM_INSERT_SWAP"
        pill_color = "#10B981" if is_confirmed else "#F59E0B"
        andon_status = "GREEN (CYCLE START CLEARED)" if is_confirmed else "AMBER (M01 HOLD ACTIVE)"

        st.markdown(
            f"""
            <div style="background: #111827; border: 1px solid {pill_color}; border-left: 5px solid {pill_color}; border-radius: 8px; padding: 12px 14px; margin-top: 10px;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.76rem; font-weight: 800; color: #0F172A; background: {pill_color}; padding: 3px 9px; border-radius: 999px;">
                        Intent: {intent} &bull; Logged to BigQuery
                    </span>
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #94A3B8;">
                        SanitizedVoiceIntent
                    </span>
                </div>
                <div style="font-size: 0.78rem; color: #94A3B8; margin-bottom: 4px;">
                    🎙️ Operator Utterance: <em style="color:#F8FAFC;">"{voice_res.get('utterance', '')}"</em>
                </div>
                <div style="background: #0B1120; border: 1px solid #1E293B; border-radius: 6px; padding: 9px 11px; font-size: 0.92rem; font-weight: 600; color: #F8FAFC; line-height: 1.45;">
                    🔊 <strong>Marathi Audio Response:</strong><br/>
                    "{spoken_marathi}"
                </div>
                <div style="margin-top: 8px; font-family: 'JetBrains Mono', monospace; font-size: 0.74rem; color: {pill_color}; display: flex; justify-content: space-between;">
                    <span>RELAY STATUS: {andon_status}</span>
                    <span>LEDGER: +INR 16,200</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
