"""
frontend/styles.py
Centralized Industrial Dark Slate HMI Design System for Vinyas (NadaTwin V2.1).
Designed for Pune-Chakan, Chennai, and Coimbatore automotive CNC machining corridors:
- Eliminates bright-white glare under shop-floor overhead LEDs & oil-mist conditions
- Enforces WCAG AAA contrast for vernacular Marathi/Hindi operator instructions
- Replaces truncated st.metric cards with responsive clamp() flex KPI cards
- Eliminates oversized markdown headers in narrow columns
"""
import streamlit as st

INDUSTRIAL_HMI_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap');

:root {
    --bg-canvas: #0B1120;
    --bg-card: #111827;
    --bg-card-elevated: #1E293B;
    --border-subtle: #1E293B;
    --border-highlight: #334155;
    --text-primary: #F8FAFC;
    --text-secondary: #94A3B8;
    --text-muted: #64748B;
    --state-green: #10B981;
    --state-green-bg: rgba(16, 185, 129, 0.12);
    --state-amber: #F59E0B;
    --state-amber-bg: rgba(245, 158, 11, 0.14);
    --state-amber-fill: #FEF3C7;
    --state-amber-ink: #0F172A;
    --state-red: #EF4444;
    --state-red-bg: rgba(239, 68, 68, 0.14);
    --accent-cyan: #38BDF8;
}

/* Global Dark Slate Canvas & Chrome Removal */
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background-color: var(--bg-canvas) !important;
    color: var(--text-primary) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

/* Hide Streamlit Deploy Button, MainMenu, Footer, and Excessive Top Padding */
[data-testid="stDeployButton"],
.stDeployButton,
#MainMenu,
footer,
[data-testid="stToolbar"] {
    display: none !important;
}

[data-testid="stHeader"] {
    background: transparent !important;
    height: 1.5rem !important;
}

.block-container {
    padding-top: 0.65rem !important;
    padding-bottom: 1.5rem !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
    max-width: 100% !important;
}

/* Streamlined Left Navigation Rail */
[data-testid="stSidebar"] {
    background-color: #080D1A !important;
    border-right: 1px solid var(--border-subtle) !important;
}
[data-testid="stSidebar"] .block-container {
    padding-top: 0.85rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
}

/* Clean Station Radio Buttons in Sidebar */
[data-testid="stSidebar"] [data-testid="stRadio"] > div {
    gap: 0.45rem !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    background-color: var(--bg-card) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 8px !important;
    padding: 0.6rem 0.75rem !important;
    width: 100% !important;
    transition: all 0.15s ease-in-out !important;
    cursor: pointer !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    border-color: var(--state-amber) !important;
    background-color: var(--bg-card-elevated) !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label p {
    font-size: 0.88rem !important;
    font-weight: 600 !important;
    color: var(--text-primary) !important;
}

/* 56px Compact Sticky Top Status Bar */
.vinyas-sticky-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 56px;
    background: linear-gradient(90deg, #0F172A 0%, #111827 100%);
    border: 1px solid var(--border-highlight);
    border-left: 4px solid var(--state-amber);
    border-radius: 8px;
    padding: 6px 14px;
    margin-bottom: 10px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
}

.vinyas-brand-cluster {
    display: flex;
    align-items: center;
    gap: 10px;
}

.vinyas-brand-title {
    font-size: 1.15rem;
    font-weight: 800;
    color: var(--text-primary);
    letter-spacing: -0.02em;
    margin: 0;
    line-height: 1.15;
}

.vinyas-brand-subtitle {
    font-size: 0.72rem;
    color: var(--text-secondary);
    font-weight: 500;
    margin: 0;
}

.vinyas-telemetry-pill {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    background-color: #0B1120;
    border: 1px solid var(--border-highlight);
    border-radius: 6px;
    padding: 6px 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    color: var(--text-primary);
    white-space: nowrap;
}

.telemetry-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: var(--state-green);
    box-shadow: 0 0 8px var(--state-green);
    display: inline-block;
}

/* Responsive Flex KPI Cards — Never Truncate with Ellipses */
.kpi-strip-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
    margin-bottom: 14px;
}

.kpi-card {
    background-color: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-top: 3px solid var(--border-highlight);
    border-radius: 8px;
    padding: 10px 14px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-width: 0;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
}
.kpi-card.kpi-emerald {
    border-top-color: var(--state-green);
}
.kpi-card.kpi-amber {
    border-top-color: var(--state-amber);
}
.kpi-card.kpi-cyan {
    border-top-color: var(--accent-cyan);
}
.kpi-card.kpi-red {
    border-top-color: var(--state-red);
}

.kpi-label {
    font-size: 0.73rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--text-secondary);
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.kpi-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: clamp(1.15rem, 1.55vw, 1.55rem);
    font-weight: 800;
    color: var(--text-primary);
    white-space: nowrap;
    line-height: 1.2;
    letter-spacing: -0.02em;
}

.kpi-sub {
    font-size: 0.74rem;
    font-weight: 600;
    color: var(--state-green);
    margin-top: 4px;
    white-space: nowrap;
}
.kpi-sub.amber {
    color: var(--state-amber);
}
.kpi-sub.cyan {
    color: var(--accent-cyan);
}
.kpi-sub.slate {
    color: var(--text-secondary);
}

/* Elevated Industrial HMI Panels & Section Headers (14px-16px) */
.hmi-panel {
    background-color: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 10px;
}

.hmi-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--border-subtle);
    padding-bottom: 8px;
    margin-bottom: 10px;
}

.hmi-section-title {
    font-size: 0.94rem; /* 15px clean section header */
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: 0.01em;
    margin: 0;
}

.hmi-pill-tag {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 999px;
    background-color: var(--bg-card-elevated);
    color: var(--accent-cyan);
    border: 1px solid var(--border-highlight);
    white-space: nowrap;
}
.hmi-pill-tag.amber {
    color: var(--state-amber);
    border-color: rgba(245, 158, 11, 0.4);
    background-color: var(--state-amber-bg);
}
.hmi-pill-tag.emerald {
    color: var(--state-green);
    border-color: rgba(16, 185, 129, 0.4);
    background-color: var(--state-green-bg);
}
.hmi-pill-tag.red {
    color: var(--state-red);
    border-color: rgba(239, 68, 68, 0.4);
    background-color: var(--state-red-bg);
}

/* Deterministic Control Dial Tiles (Column 2) */
.dial-grid-3 {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
    margin-bottom: 10px;
}

.dial-tile {
    background-color: #161F30;
    border: 1px solid var(--border-highlight);
    border-top: 3px solid var(--state-amber);
    border-radius: 7px;
    padding: 8px 10px;
    text-align: center;
}
.dial-tile.cyan-top {
    border-top-color: var(--accent-cyan);
}
.dial-tile-label {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    color: var(--text-secondary);
    letter-spacing: 0.03em;
}
.dial-tile-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: clamp(1.1rem, 1.4vw, 1.4rem);
    font-weight: 800;
    color: var(--text-primary);
    margin: 3px 0;
    white-space: nowrap;
}
.dial-tile-window {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem;
    color: var(--state-amber);
    white-space: nowrap;
}
.dial-tile.cyan-top .dial-tile-window {
    color: var(--accent-cyan);
}

/* PPAP Verification Badges (Column 3) */
.ppap-banner-pass {
    background-color: var(--state-green-bg);
    border: 1px solid var(--state-green);
    border-left: 5px solid var(--state-green);
    border-radius: 6px;
    padding: 9px 12px;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.ppap-banner-title {
    font-size: 0.88rem;
    font-weight: 800;
    color: #34D399;
    letter-spacing: 0.02em;
}

.ppap-badge-pass {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background-color: #161F30;
    border: 1px solid var(--border-subtle);
    border-left: 4px solid var(--state-green);
    border-radius: 6px;
    padding: 7px 10px;
    margin-bottom: 6px;
    font-size: 0.8rem;
}
.ppap-badge-fail {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background-color: #161F30;
    border: 1px solid var(--border-subtle);
    border-left: 4px solid var(--state-red);
    border-radius: 6px;
    padding: 7px 10px;
    margin-bottom: 6px;
    font-size: 0.8rem;
}
.ppap-badge-name {
    font-weight: 600;
    color: var(--text-primary);
}
.ppap-badge-val {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.74rem;
    color: #34D399;
    white-space: nowrap;
}

.security-lock-badge {
    background-color: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.35);
    border-radius: 6px;
    padding: 8px 10px;
    margin-top: 8px;
    font-size: 0.76rem;
    color: #FCA5A5;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

/* Operator Vernacular Card — WCAG AAA Contrast Fix */
.operator-vernacular-card {
    background-color: #1E293B;
    border: 1px solid #475569;
    border-left: 6px solid #F59E0B;
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 14px;
    box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4);
}

.operator-amber-callout {
    background-color: #FEF3C7;
    color: #0F172A !important;
    border: 2px solid #F59E0B;
    border-radius: 8px;
    padding: 14px 16px;
    margin: 12px 0;
    font-size: clamp(1.25rem, 1.6vw, 1.55rem); /* 20px-25px bold readable Marathi */
    font-weight: 800;
    line-height: 1.45;
}

.step-tile-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
    margin-top: 12px;
}

.step-tile {
    background-color: #0F172A;
    border: 1px solid #334155;
    border-top: 3px solid #F59E0B;
    border-radius: 8px;
    padding: 12px;
}
.step-tile-num {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    font-weight: 800;
    color: #F59E0B;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.step-tile-title {
    font-size: 1.02rem;
    font-weight: 800;
    color: #F8FAFC;
    margin: 4px 0;
}
.step-tile-desc {
    font-size: 0.8rem;
    color: #CBD5E1;
    line-height: 1.35;
}

/* Ergonomic 40mm Palm-Button PTT Simulator (min-height: 88px) */
.ptt-pod-container {
    background-color: var(--bg-card);
    border: 1px solid var(--border-highlight);
    border-radius: 10px;
    padding: 16px;
}

div.stButton > button[kind="primary"] {
    background: linear-gradient(180deg, #F59E0B 0%, #D97706 100%) !important;
    color: #0F172A !important;
    font-weight: 800 !important;
    border: 2px solid #FBBF24 !important;
    border-radius: 8px !important;
    letter-spacing: 0.02em !important;
    box-shadow: 0 4px 12px rgba(245, 158, 11, 0.25) !important;
}
div.stButton > button[kind="primary"]:hover {
    background: linear-gradient(180deg, #FBBF24 0%, #F59E0B 100%) !important;
    color: #0F172A !important;
    border-color: #FEF3C7 !important;
}

/* Specific Palm-Button Wrapper Override for 88px Glove-Friendly Target */
.palm-btn-scope div.stButton > button {
    min-height: 88px !important;
    font-size: 1.15rem !important;
    font-weight: 900 !important;
    background: linear-gradient(180deg, #EF4444 0%, #B91C1C 100%) !important;
    color: #F8FAFC !important;
    border: 3px solid #FCA5A5 !important;
    border-radius: 12px !important;
    box-shadow: 0 6px 18px rgba(239, 68, 68, 0.35) !important;
}
.palm-btn-scope div.stButton > button:hover {
    background: linear-gradient(180deg, #F87171 0%, #DC2626 100%) !important;
    transform: translateY(-1px);
}

/* ============================================================================
   ISA-101 HIGH-PERFORMANCE HMI OPERATOR SCREEN (3-Second Glanceable)
   Flat neutral dark slate (#0F172A) base; color ONLY for actionable anomalies
   ============================================================================ */
.isa101-top-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 72px;
    min-height: 72px;
    background-color: #0F172A;
    border: 2px solid #1E293B;
    border-radius: 10px;
    padding: 0 20px;
    margin-bottom: 16px;
}

.isa101-machine-id {
    font-family: 'Inter', sans-serif;
    font-size: clamp(1.35rem, 2vw, 1.75rem);
    font-weight: 900;
    color: #F8FAFC;
    letter-spacing: 0.02em;
    white-space: nowrap;
}

.isa101-status-pill-normal {
    background-color: #1E293B;
    color: #94A3B8;
    border: 2px solid #334155;
    border-radius: 8px;
    padding: 10px 22px;
    font-size: clamp(1.05rem, 1.5vw, 1.35rem);
    font-weight: 800;
    letter-spacing: 0.03em;
    white-space: nowrap;
}

.isa101-status-pill-hold {
    background-color: #F59E0B;
    color: #0F172A;
    border: 2px solid #FBBF24;
    border-radius: 8px;
    padding: 10px 22px;
    font-size: clamp(1.05rem, 1.5vw, 1.35rem);
    font-weight: 900;
    letter-spacing: 0.03em;
    white-space: nowrap;
}

.isa101-status-pill-stop {
    background-color: #EF4444;
    color: #FFFFFF;
    border: 2px solid #FCA5A5;
    border-radius: 8px;
    padding: 10px 22px;
    font-size: clamp(1.05rem, 1.5vw, 1.35rem);
    font-weight: 900;
    letter-spacing: 0.03em;
    white-space: nowrap;
}

.isa101-lang-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 0.95rem;
    font-weight: 700;
    color: #94A3B8;
    white-space: nowrap;
}
.isa101-lang-active {
    background-color: #334155;
    color: #F8FAFC;
    padding: 3px 9px;
    border-radius: 5px;
    font-weight: 900;
}

/* Block 2: Giant 48px Numbered Action Cards (#F8FAFC on #1E293B, #F59E0B 6px border) */
.isa101-action-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
}

.isa101-action-card {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-left: 6px solid #F59E0B;
    border-radius: 10px;
    padding: 22px 18px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-height: 220px;
}

.isa101-step-header {
    font-size: 0.92rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #F59E0B;
}

.isa101-giant-value {
    font-family: 'JetBrains Mono', 'Inter', monospace;
    font-size: 48px;
    font-weight: 900;
    color: #F8FAFC;
    line-height: 1.08;
    margin: 14px 0;
    letter-spacing: -0.02em;
    white-space: nowrap;
}

.isa101-sub-label {
    font-size: 1.18rem;
    font-weight: 700;
    color: #F8FAFC;
    line-height: 1.35;
}

.isa101-normal-calm-card {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-left: 6px solid #475569;
    border-radius: 10px;
    padding: 48px 28px;
    min-height: 220px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
}

/* Block 3: Fitts's Law 220px Palm-Button & Emerald Confirmation Card */
.isa101-palm-scope div.stButton > button {
    min-height: 220px !important;
    width: 100% !important;
    background-color: #EF4444 !important;
    background-image: none !important;
    color: #FFFFFF !important;
    border: 4px solid #F59E0B !important;
    border-radius: 14px !important;
    padding: 18px 16px !important;
    font-size: 1.55rem !important;
    font-weight: 900 !important;
    line-height: 1.35 !important;
    white-space: pre-line !important;
    box-shadow: none !important;
    cursor: pointer !important;
}
.isa101-palm-scope div.stButton > button:hover {
    background-color: #DC2626 !important;
    border-color: #FEF3C7 !important;
}
.isa101-palm-scope div.stButton > button p {
    font-size: 1.45rem !important;
    font-weight: 900 !important;
    color: #FFFFFF !important;
    line-height: 1.4 !important;
}

.isa101-palm-zone {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.isa101-confirmed-card {
    background-color: #10B981;
    color: #0F172A;
    border: 3px solid #A7F3D0;
    border-radius: 12px;
    min-height: 220px;
    padding: 24px 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
}
.isa101-confirmed-title {
    font-size: clamp(1.35rem, 1.8vw, 1.7rem);
    font-weight: 900;
    color: #0F172A;
    letter-spacing: 0.01em;
    line-height: 1.25;
}
.isa101-confirmed-sub {
    font-size: 1.12rem;
    font-weight: 800;
    color: #064E3B;
    margin-top: 10px;
}

@keyframes isa101-pulse {
    0% { opacity: 1; }
    50% { opacity: 0.65; }
    100% { opacity: 1; }
}
.isa101-listening-card {
    background-color: #F59E0B;
    color: #0F172A;
    border: 3px solid #FEF3C7;
    border-radius: 12px;
    min-height: 220px;
    padding: 24px 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    animation: isa101-pulse 0.8s infinite ease-in-out;
}

/* Dual Cryptographic Certificate Card (Persona 3 QA) */
.dual-cert-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    margin-top: 10px;
}
.cert-layer-card {
    background-color: #0F172A;
    border: 1px solid #334155;
    border-radius: 7px;
    padding: 10px 12px;
}
.cert-layer-title {
    font-size: 0.74rem;
    font-weight: 700;
    text-transform: uppercase;
    color: var(--accent-cyan);
    letter-spacing: 0.04em;
    margin-bottom: 4px;
}
.cert-hash-mono {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.74rem;
    color: #E2E8F0;
    background: #0B1120;
    padding: 5px 8px;
    border-radius: 4px;
    border: 1px solid #1E293B;
    word-break: break-all;
}

/* Scenario Trigger Cards (Persona 4 Studio) */
.scenario-card {
    background-color: #161F30;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 8px;
    transition: all 0.15s ease;
}
.scenario-card.active-amber {
    border: 2px solid #F59E0B;
    background-color: rgba(245, 158, 11, 0.10);
}
.scenario-card.active-emerald {
    border: 2px solid #10B981;
    background-color: rgba(16, 185, 129, 0.10);
}
</style>
"""


def inject_industrial_hmi_css() -> None:
    """Injects the centralized Industrial Dark Slate HMI theme into the active Streamlit page."""
    st.markdown(INDUSTRIAL_HMI_CSS, unsafe_allow_html=True)


def render_kpi_card(
    label: str,
    value: str,
    subtitle: str,
    accent: str = "emerald",
    sub_color: str = "emerald",
) -> str:
    """Returns compact HTML for a single responsive, non-truncating flex KPI card."""
    return (
        f'<div class="kpi-card kpi-{accent}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-sub {sub_color}">{subtitle}</div>'
        f"</div>"
    )
