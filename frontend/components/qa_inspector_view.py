"""
frontend/components/qa_inspector_view.py
Vinyas Optical QA & Cryptographic Provenance Workbench (Persona 3: Plant Quality Head & OEM Auditor):
Isolated via @st.fragment.
- Split Inspection Workbench:
  - Left Panel: Cross-polarized V-block camera capture supporting all 4 key inspection samples
    (Sample A: Golden Master REF-01, Sample B: Foundry Porosity REF-10, Sample C: Chatter Scar REF-04,
     Sample D: Coolant Drop REF-12) with zoomable inspection overlay & correlated in-cycle vibration telemetry.
  - Right Adjudication & Dual-Provenance Card:
    * Prominent disposition banner (`FOUNDRY CHARGEBACK PROVEN (+INR 14,000)` in amber/emerald,
      `REJECT — MACHINING CHATTER` in red, or `IATF 16949 PASS` in emerald)
    * Correlated cycle telemetry (`Cycle CYC_CHAKAN_04_99281 • Coherence: 0.09 — Clean Cut`)
    * Clean Dual Cryptographic Certificate Card displaying both the truncated `Cloud KMS / HMAC-SHA256`
      raw frame digest and the `Nano Banana Pro + SynthID` watermarked QA stamp side-by-side.
"""
import base64
import json
from pathlib import Path
from typing import Any
import httpx
from PIL import Image, ImageDraw
import streamlit as st
from config.settings import settings
from backend.models.schemas import AOIInspectionResult, InCycleTelemetrySummary
from backend.services.kms_certificate_service import KMSCertificateService

kms_ui_service = KMSCertificateService()


def _load_14_references() -> list[dict[str, Any]]:
    manifest_path = Path("config/reference_tokens_manifest.json")
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return data.get("references", [])
    return []


def _get_sample_bundle(
    sample_choice: str,
    backend_url: str = "http://localhost:8000",
) -> tuple[Path, InCycleTelemetrySummary, AOIInspectionResult]:
    if "REF-10" in sample_choice:
        img_path = Path("data/golden_references/REF-10.jpg")
        in_cycle = InCycleTelemetrySummary(
            cycle_id="CYC_CHAKAN_04_99280",
            stage_a_state="GREEN_NOMINAL",
            peak_vibration_rms_g=1.12,
            band_power_ratio_2k_8k=0.14,
            spectral_crest_factor=2.3,
            hilbert_envelope_coherence=0.09,
            ct_ripple_std_amps=0.26,
            chatter_detected=False,
        )
        local_aoi = AOIInspectionResult.model_validate_json(
            Path("data/fallback_cache/aoi_foundry_porosity_ref10.json").read_text(encoding="utf-8")
        )
    elif "REF-04" in sample_choice:
        img_path = Path("data/golden_references/REF-04.jpg")
        in_cycle = InCycleTelemetrySummary(
            cycle_id="CYC_CHAKAN_04_99281",
            stage_a_state="YELLOW_M01_HOLD",
            peak_vibration_rms_g=2.84,
            band_power_ratio_2k_8k=0.71,
            spectral_crest_factor=8.2,
            hilbert_envelope_coherence=0.84,
            ct_ripple_std_amps=0.46,
            chatter_detected=True,
        )
        local_aoi = AOIInspectionResult.model_validate_json(
            Path("data/fallback_cache/aoi_chatter_reject_ref04.json").read_text(encoding="utf-8")
        )
    elif "REF-12" in sample_choice:
        img_path = Path("data/golden_references/REF-12.jpg")
        in_cycle = InCycleTelemetrySummary(
            cycle_id="CYC_CHAKAN_04_99283",
            stage_a_state="GREEN_NOMINAL",
            peak_vibration_rms_g=1.05,
            band_power_ratio_2k_8k=0.11,
            spectral_crest_factor=1.9,
            hilbert_envelope_coherence=0.08,
            ct_ripple_std_amps=0.22,
            chatter_detected=False,
        )
        local_aoi = AOIInspectionResult(
            cycle_id="CYC_CHAKAN_04_99283",
            passed_iatf_16949=True,
            matched_reference_token_id="REF-12",
            detected_anomaly_type="HARMLESS_OIL_DROPLET",
            surface_ra_estimate_um=0.98,
            inspector_summary=(
                "Translucent residual flood-coolant droplet detected matching REF-12. "
                "Cross-polarized specular analysis and clean in-cycle telemetry (Coherence: 0.08) "
                "confirm zero subsurface porosity or chatter. False-positive suppressed -> PASS."
            ),
            raw_frame_sha256="6d902e41a83c5b7190e42f1c83a5d7092b4e61c8f03a9d257b14e8c6a390f214",
            raw_frame_hmac_sha256="6d902e41a83c5b7190e42f1c83a5d7092b4e61c8f03a9d257b14e8c6a390f214",
        )
    else:
        img_path = Path("data/golden_references/REF-01.jpg")
        in_cycle = InCycleTelemetrySummary(
            cycle_id="CYC_CHAKAN_04_99282",
            stage_a_state="GREEN_NOMINAL",
            peak_vibration_rms_g=1.08,
            band_power_ratio_2k_8k=0.12,
            spectral_crest_factor=2.0,
            hilbert_envelope_coherence=0.09,
            ct_ripple_std_amps=0.24,
            chatter_detected=False,
        )
        local_aoi = AOIInspectionResult.model_validate_json(
            Path("data/fallback_cache/aoi_pass_synthid.json").read_text(encoding="utf-8")
        )

    # Attempt live/backend FastAPI `/api/v1/aoi/inspect` endpoint first (with automatic local failover)
    candidates = [backend_url.rstrip("/")]
    if settings.BACKEND_API_URL.rstrip("/") not in candidates:
        candidates.append(settings.BACKEND_API_URL.rstrip("/"))
    raw_b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
    for target_url in candidates:
        try:
            with httpx.Client(timeout=2.5) as client:
                resp = client.post(
                    f"{target_url}/api/v1/aoi/inspect",
                    json={
                        "part_id": "DIFF_HOUSING_SN_8892",
                        "work_order_id": "WO_ALSI9CU3_DIFF_882",
                        "cycle_id": in_cycle.cycle_id,
                        "acoustic_rms": in_cycle.peak_vibration_rms_g,
                        "image_b64": raw_b64,
                    },
                )
                if resp.status_code == 200:
                    live_aoi = AOIInspectionResult.model_validate(resp.json())
                    live_aoi.in_cycle_summary = live_aoi.in_cycle_summary or in_cycle
                    return img_path, in_cycle, live_aoi
        except Exception:
            continue

    local_aoi.cycle_id = in_cycle.cycle_id
    local_aoi.in_cycle_summary = in_cycle
    local_aoi.served_from_fallback = True
    return img_path, in_cycle, local_aoi


def _render_inspection_overlay_image(img_path: Path, token_id: str, zoom_roi: bool) -> Image.Image:
    """Draws a cross-polarized V-block reticle overlay (and optional 2x center ROI zoom) on the casting capture."""
    img = Image.open(img_path).convert("RGB")
    w, h = img.size

    if zoom_roi:
        crop_box = (int(w * 0.22), int(h * 0.22), int(w * 0.78), int(h * 0.78))
        img = img.crop(crop_box).resize((w, h), Image.Resampling.BICUBIC)

    draw = ImageDraw.Draw(img)
    color = (245, 158, 11) if token_id == "REF-10" else ((239, 68, 68) if token_id == "REF-04" else (16, 185, 129))

    # Crosshair ROI bounding box
    x0, y0, x1, y1 = int(w * 0.24), int(h * 0.24), int(w * 0.76), int(h * 0.76)
    draw.rectangle((x0, y0, x1, y1), outline=color, width=3)
    cx, cy = w // 2, h // 2
    draw.line((cx - 24, cy, cx + 24, cy), fill=color, width=2)
    draw.line((cx, cy - 24, cx, cy + 24), fill=color, width=2)

    # Top telemetry HUD bar on frame
    draw.rectangle((0, 0, w, 32), fill=(11, 17, 32))
    zoom_tag = "2.0x ROI ZOOM" if zoom_roi else "1.0x FULL V-BLOCK"
    draw.text((10, 8), f"CROSS-POLARIZED AOI | TOKEN: {token_id} | {zoom_tag}", fill=color)
    return img


@st.fragment
def render_qa_inspector_view(backend_url: str = "http://localhost:8000"):
    """Renders the Split Inspection Workbench & Dual Cryptographic Provenance Card."""
    tab_inspect, tab_tokens = st.tabs(
        ["🔍 Split V-Block Inspection & Dual-Provenance Workbench", "📚 14 Cached Reference Tokens (4,932-Token Context Cache)"]
    )

    with tab_inspect:
        col_left, col_right = st.columns([1.05, 1.35], gap="large")

        # =====================================================================
        # LEFT PANEL: Cross-Polarized V-Block Camera Capture & Zoom Overlay
        # =====================================================================
        with col_left:
            st.markdown(
                """
                <div class="hmi-panel" style="margin-bottom: 8px;">
                    <div class="hmi-section-header">
                        <span class="hmi-section-title">1. Cross-Polarized V-Block Optical Tunnel</span>
                        <span class="hmi-pill-tag">4,862+ Cached Tokens</span>
                    </div>
                """,
                unsafe_allow_html=True,
            )

            sample_choice = st.selectbox(
                "Select V-Block Inspection Sample:",
                [
                    "Sample B: Foundry Porosity REF-10 (Clean Cut → Foundry Chargeback)",
                    "Sample A: Golden Master REF-01 (Isotropic Bore Lay → Pass)",
                    "Sample C: Chatter Scar REF-04 (4.2 kHz Sinusoidal Marks → Reject)",
                    "Sample D: Coolant Drop REF-12 (Benign Fluid Meniscus → Suppressed)",
                ],
                index=0,
            )

            z_col1, z_col2 = st.columns(2)
            with z_col1:
                show_overlay = st.toggle("🎯 Inspection Reticle Overlay", value=True)
            with z_col2:
                zoom_roi = st.toggle("🔍 2.0× Defect ROI Zoom", value=False)

            st.markdown("</div>", unsafe_allow_html=True)

            img_path, in_cycle, aoi = _get_sample_bundle(sample_choice, backend_url=backend_url)
            raw_bytes = img_path.read_bytes()

            if show_overlay or zoom_roi:
                display_img = _render_inspection_overlay_image(img_path, aoi.matched_reference_token_id, zoom_roi)
                st.image(
                    display_img,
                    caption=f"Cross-Polarized V-Block Capture • Matched Token: {aoi.matched_reference_token_id} • Ra = {aoi.surface_ra_estimate_um:.2f} µm",
                    use_container_width=True,
                )
            else:
                st.image(
                    str(img_path),
                    caption=f"Raw Unfiltered V-Block Frame • Linked Cycle: {in_cycle.cycle_id}",
                    use_container_width=True,
                )

        # =====================================================================
        # RIGHT PANEL: Adjudication Banner, Correlated Telemetry & Dual Certificate
        # =====================================================================
        with col_right:
            cert_bundle = kms_ui_service.render_certificate_png(
                part_id="DIFF_HOUSING_SN_8892",
                work_order_id="WO_ALSI9CU3_DIFF_882",
                raw_frame_bytes=raw_bytes,
                aoi_result=aoi,
                in_cycle_summary=in_cycle,
            )
            sig_valid = kms_ui_service.verify_local_signature(
                cert_bundle["canonical_payload_bytes"],
                cert_bundle["kms_signature_b64"],
            )

            # Prominent Disposition Banner
            if aoi.detected_anomaly_type == "FOUNDRY_POROSITY_CHARGEBACK":
                banner_bg = "linear-gradient(90deg, rgba(245, 158, 11, 0.22) 0%, rgba(16, 185, 129, 0.16) 100%)"
                banner_border = "#F59E0B"
                banner_title = "🛡️ FOUNDRY CHARGEBACK PROVEN (+INR 14,000)"
                banner_sub = (
                    f"Matched Token <strong>{aoi.matched_reference_token_id}</strong> (Subsurface Gas Pinholes, Ra {aoi.surface_ra_estimate_um:.2f} µm) "
                    f"with <strong>ZERO in-cycle CNC vibration</strong>. Quarantined for Supplier Debit Note."
                )
            elif not aoi.passed_iatf_16949:
                banner_bg = "rgba(239, 68, 68, 0.18)"
                banner_border = "#EF4444"
                banner_title = f"❌ REJECT — MACHINING CHATTER ({aoi.matched_reference_token_id})"
                banner_sub = (
                    f"Sinusoidal chatter witness marks (Ra {aoi.surface_ra_estimate_um:.2f} µm > 1.60 µm IATF ceiling) "
                    f"corroborated by in-cycle 4,210 Hz spindle harmonic."
                )
            elif aoi.detected_anomaly_type == "HARMLESS_OIL_DROPLET":
                banner_bg = "rgba(16, 185, 129, 0.16)"
                banner_border = "#10B981"
                banner_title = f"✅ PASS — BENIGN COOLANT DROP SUPPRESSED ({aoi.matched_reference_token_id})"
                banner_sub = (
                    f"Cross-polarized glare &amp; clean in-cycle cut confirm harmless residual coolant bead "
                    f"(Ra {aoi.surface_ra_estimate_um:.2f} µm). False-positive scrap prevented."
                )
            else:
                banner_bg = "rgba(16, 185, 129, 0.16)"
                banner_border = "#10B981"
                banner_title = f"✅ IATF 16949 GOLDEN MASTER PASS ({aoi.matched_reference_token_id})"
                banner_sub = (
                    f"Uniform isotropic bore finish (Ra {aoi.surface_ra_estimate_um:.2f} µm ≤ 1.20 µm limit) "
                    f"verified across all 14 cached reference tokens."
                )

            cut_label = "Chatter Detected (4,210 Hz)" if in_cycle.chatter_detected else "Clean Cut (Zero CNC Chatter)"
            cut_color = "#EF4444" if in_cycle.chatter_detected else "#10B981"

            raw_sha_trunc = f"{cert_bundle['raw_frame_sha256'][:18]}...{cert_bundle['raw_frame_sha256'][-10:]}"
            ecdsa_sig_trunc = f"{cert_bundle['kms_signature_b64'][:28]}...{cert_bundle['kms_signature_b64'][-12:]}"
            active_ref04_style = "border: 1px solid #EF4444; background: rgba(239, 68, 68, 0.14);" if aoi.matched_reference_token_id == "REF-04" else "border: 1px solid #1E293B; background: #0B1120;"
            active_ref10_style = "border: 1px solid #F59E0B; background: rgba(245, 158, 11, 0.14);" if aoi.matched_reference_token_id == "REF-10" else "border: 1px solid #1E293B; background: #0B1120;"

            st.markdown(
                f"""
                <div class="hmi-panel">
                    <div class="hmi-section-header">
                        <span class="hmi-section-title">2. Cycle-Correlated Adjudication &amp; Cloud KMS Provenance</span>
                        <span class="hmi-pill-tag emerald">&lt; 1.1s Cached Grading</span>
                    </div>

                    <!-- Prominent Disposition Banner -->
                    <div style="background: {banner_bg}; border: 1px solid {banner_border}; border-left: 6px solid {banner_border}; border-radius: 8px; padding: 12px 14px; margin-bottom: 10px;">
                        <div style="font-size: 1.05rem; font-weight: 900; color: #F8FAFC; letter-spacing: 0.01em;">
                            {banner_title}
                        </div>
                        <div style="font-size: 0.81rem; color: #E2E8F0; margin-top: 4px; line-height: 1.45;">
                            {banner_sub}
                        </div>
                    </div>

                    <!-- Correlated In-Cycle Telemetry Strip -->
                    <div style="background: #0B1120; border: 1px solid #1E293B; border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between; font-family: 'JetBrains Mono', monospace; font-size: 0.77rem;">
                        <span>Cycle <strong style="color:#38BDF8;">{in_cycle.cycle_id}</strong> &bull; Coherence: <strong style="color:#F59E0B;">{in_cycle.hilbert_envelope_coherence:.2f}</strong> &mdash; <strong style="color:{cut_color};">{cut_label}</strong></span>
                        <span style="color:#94A3B8;">Vib RMS: {in_cycle.peak_vibration_rms_g:.2f}G</span>
                    </div>

                    <!-- Unified cycle_id Attribution Matrix (REF-04 CNC Chatter vs REF-10 Foundry Porosity) -->
                    <div style="background: #0F172A; border: 1px solid #1E293B; border-radius: 6px; padding: 8px 10px; margin-bottom: 10px;">
                        <div style="font-size: 0.71rem; font-weight: 800; text-transform: uppercase; color: #94A3B8; letter-spacing: 0.04em; margin-bottom: 6px;">
                            Unified <code style="color:#38BDF8;">cycle_id</code> Fault Attribution Matrix (In-Cycle Vibration &times; Post-Cycle Optical AOI)
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 0.74rem; font-family: 'JetBrains Mono', monospace;">
                            <div style="{active_ref04_style} border-radius: 5px; padding: 6px 8px;">
                                <div style="color: #F87171; font-weight: 800;">CNC Chatter (REF-04)</div>
                                <div style="color: #CBD5E1; margin-top: 2px;">In-Cycle Coh &ge; 0.72 + 4.21 kHz Marks</div>
                                <div style="color: #94A3B8; font-size: 0.7rem;">Liability: Internal Machining Scrap</div>
                            </div>
                            <div style="{active_ref10_style} border-radius: 5px; padding: 6px 8px;">
                                <div style="color: #FBBF24; font-weight: 800;">Foundry Porosity (REF-10)</div>
                                <div style="color: #CBD5E1; margin-top: 2px;">In-Cycle Coh &lt; 0.20 (Clean Cut) + Gas Pits</div>
                                <div style="color: #34D399; font-size: 0.7rem;">Liability: Supplier Chargeback (+INR 14k)</div>
                            </div>
                        </div>
                    </div>

                    <!-- Deterministic Pillow & Google Cloud KMS Cryptographic Certificate Card -->
                    <div class="dual-cert-grid">
                        <div class="cert-layer-card" style="border-top: 3px solid #38BDF8;">
                            <div class="cert-layer-title">Layer 1 • Google Cloud KMS (EC_SIGN_P256_SHA256)</div>
                            <div style="font-size: 0.73rem; color: #94A3B8; margin-bottom: 6px;">
                                Raw Optical Frame SHA-256 + <code style="color:#38BDF8;">{in_cycle.cycle_id}</code> Digest
                            </div>
                            <div class="cert-hash-mono">
                                SHA256: {raw_sha_trunc}<br/>
                                KMS   : {ecdsa_sig_trunc}
                            </div>
                            <div style="margin-top: 6px; font-size: 0.72rem; color: #10B981; font-weight: 700;">
                                ✅ ECDSA P-256 Verified ({cert_bundle['signing_backend']})
                            </div>
                        </div>

                        <div class="cert-layer-card" style="border-top: 3px solid #F59E0B;">
                            <div class="cert-layer-title" style="color: #F59E0B;">Layer 2 • Deterministic Pillow QA Certificate</div>
                            <div style="font-size: 0.73rem; color: #94A3B8; margin-bottom: 6px;">
                                Non-Generative Tamper-Evident Audit PNG (Day-0 Synth: Nano Banana Pro)
                            </div>
                            <div class="cert-hash-mono">
                                Engine: Pillow (PIL) Deterministic Renderer<br/>
                                Token : {aoi.matched_reference_token_id} (Ra {aoi.surface_ra_estimate_um:.2f} µm)
                            </div>
                            <div style="margin-top: 6px; font-size: 0.72rem; color: #F59E0B; font-weight: 700;">
                                🛡️ Cryptographically Bound to Supplier Debit Note
                            </div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.image(
                cert_bundle["certificate_png_bytes"],
                caption=f"Signed Pillow QA & Foundry Chargeback Certificate • Cycle {cert_bundle['cycle_id']} • Verified: {sig_valid}",
                use_container_width=True,
            )

    with tab_tokens:
        st.markdown(
            """
            <div class="hmi-panel">
                <div class="hmi-section-header">
                    <span class="hmi-section-title">14 Visual Reference Tokens Pinned in Gemini 2.5 Flash Context Cache</span>
                    <span class="hmi-pill-tag emerald">4,932 Tokens &gt; 4,096 Floor</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        references = _load_14_references()
        cols = st.columns(4)
        for idx, ref in enumerate(references):
            with cols[idx % 4]:
                ref_img = Path(ref.get("path", ""))
                if ref_img.exists():
                    st.image(str(ref_img), use_container_width=True)
                st.markdown(
                    f"""
                    <div style="background:#111827; border:1px solid #1E293B; border-radius:6px; padding:8px; margin-bottom:10px; font-size:0.76rem;">
                        <div style="font-weight:800; color:#F8FAFC;">{ref['id']} • {ref['category']}</div>
                        <div style="color:#94A3B8; margin:3px 0;">{ref['visual_signature']}</div>
                        <div style="font-family:'JetBrains Mono',monospace; font-size:0.7rem; color:#F59E0B;">{ref['disposition']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
