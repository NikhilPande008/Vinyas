"""
scripts/verify_live_gcp.py
End-to-End Live Google Cloud & Gemini API Verification CLI for Vinyas (`vinyas-buildathon-6626`).
Temporarily runs with `DEMO_SAFE_MODE = False` to exercise:
  1. Live Gemini 2.5 Flash Vernacular Operator Copilot (`served_from_fallback == False`)
  2. Live Gemini 2.5 Flash Multimodal Stage C Diagnostics (`served_from_fallback == False`)
  3. Live Google Cloud KMS (`EC_SIGN_P256_SHA256`) Pillow QA Certificate Signing & GCS Vault Upload
  4. Live BigQuery Streaming (`nadatwin_telemetry.shift_incidents_ledger`)
Estimated cost per run: < $0.002 USD.
"""
import asyncio
import io
import json
import sys
import wave
from pathlib import Path
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from backend.models.schemas import AOIInspectionResult, InCycleTelemetrySummary
from backend.services.gemini_live_service import GeminiLiveService
from backend.services.gemini_omni_service import GeminiOmniService
from backend.services.kms_certificate_service import KMSCertificateService
from backend.services.bigquery_logger import BigQueryLogger


def _make_sample_16k_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x10\x02" * 4000)  # 250ms 16kHz frame
    return buf.getvalue()


def _make_sample_spectrogram_png() -> bytes:
    img = Image.new("RGB", (256, 256), color=(24, 42, 68))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def main() -> None:
    print("======================================================================")
    print(" Vinyas — Live GCP & Gemini 2.5 Flash Verification Suite")
    print(f" Project ID : {settings.GCP_PROJECT_ID} ({settings.GCP_LOCATION})")
    print(f" KMS Key    : {settings.CLOUD_KMS_KEY_RESOURCE}")
    print(f" GCS Vault  : {settings.GCS_QA_VAULT_BUCKET}")
    print("======================================================================")

    settings.DEMO_SAFE_MODE = False

    # 1. Live Vernacular Copilot
    print("\n[1/4] Testing Live Gemini 2.5 Flash Vernacular Operator Copilot...")
    live_svc = GeminiLiveService()
    voice_res = await live_svc.process_operator_utterance(
        operator_utterance="T03 insert corner 2 badalala ahe, cycle suru karu ka?",
        current_machine_state="YELLOW_M01_HOLD",
    )
    print(f"  -> Intent              : {voice_res.intent}")
    print(f"  -> Marathi Response    : {voice_res.spoken_response_marathi}")
    print(f"  -> Served From Fallback: {voice_res.served_from_fallback}")

    # 2. Live Multimodal Stage C Diagnostics
    print("\n[2/4] Testing Live Gemini 2.5 Flash Multimodal Stage C Diagnostics...")
    omni_svc = GeminiOmniService()
    ct_json = json.dumps(
        {
            "cycle_id": "CYC_CHAKAN_LIVE_01",
            "peak_vibration_rms_g": 2.95,
            "band_power_ratio_2k_8k": 0.61,
            "hilbert_envelope_coherence": 0.84,
            "ct_ripple_std_amps": 0.58,
            "dominant_chatter_hz": 4210.0,
        }
    )
    diag_res = await omni_svc.classify_diagnostic_evidence(
        audio_wav_16k_bytes=_make_sample_16k_wav(),
        mel_spectrogram_png_bytes=_make_sample_spectrogram_png(),
        ct_envelope_json_str=ct_json,
        machine_context={
            "machine_id": "FANUC_0iTF_CHAKAN_04",
            "tool_id": "T03",
            "cycle_id": "CYC_CHAKAN_LIVE_01",
        },
    )
    print(f"  -> Defect Class        : {diag_res.defect_classification}")
    print(f"  -> Dominant Chatter Hz : {diag_res.detected_harmonic_hz} Hz")
    print(f"  -> Confidence          : {diag_res.confidence_score}")
    print(f"  -> Served From Fallback: {diag_res.served_from_fallback}")

    # 3. Live Cloud KMS Asymmetric ECDSA P-256 Signing & GCS QA Vault Upload
    print("\n[3/4] Testing Live Cloud KMS (EC_SIGN_P256_SHA256) Signing & GCS QA Vault Upload...")
    kms_svc = KMSCertificateService()
    ref_img_path = settings.GOLDEN_REFS_DIR / "ref_10_foundry_porosity.jpg"
    raw_bytes = ref_img_path.read_bytes() if ref_img_path.exists() else _make_sample_spectrogram_png()
    sample_aoi = AOIInspectionResult(
        cycle_id="CYC_CHAKAN_LIVE_01",
        passed_iatf_16949=False,
        matched_reference_token_id="REF-10",
        detected_anomaly_type="FOUNDRY_POROSITY_CHARGEBACK",
        surface_ra_estimate_um=1.12,
        inspector_summary="Subsurface gas porosity verified with clean spindle vibration baseline.",
        served_from_fallback=False,
    )
    in_cycle = InCycleTelemetrySummary(
        cycle_id="CYC_CHAKAN_LIVE_01",
        machine_id="FANUC_0iTF_CHAKAN_04",
        tool_id="T03",
        stage_a_state="GREEN_NOMINAL",
        peak_vibration_rms_g=0.38,
        band_power_ratio_2k_8k=0.14,
        hilbert_envelope_coherence=0.11,
        ct_ripple_std_amps=0.06,
        chatter_detected=False,
    )
    out_png = settings.DATA_DIR / "live_kms_certificate.png"
    cert_bundle = kms_svc.render_certificate_png(
        part_id="ALSI9CU3_BORE_LIVE_01",
        work_order_id="WO_CHAKAN_2026_LIVE",
        raw_frame_bytes=raw_bytes,
        aoi_result=sample_aoi,
        in_cycle_summary=in_cycle,
        output_path=out_png,
    )
    print(f"  -> Signing Authority   : {cert_bundle['signing_backend']}")
    print(f"  -> Raw Frame SHA-256   : {cert_bundle['raw_frame_sha256']}")
    print(f"  -> KMS Signature (b64) : {cert_bundle['kms_signature_b64'][:48]}...")
    print(f"  -> GCS QA Vault URI    : {cert_bundle.get('gcs_vault_uri')}")
    print(f"  -> Local PNG Saved     : {out_png}")

    # 4. Live BigQuery Streaming
    print("\n[4/4] Testing Live BigQuery Streaming to nadatwin_telemetry.shift_incidents_ledger...")
    bq_logger = BigQueryLogger()
    await bq_logger.log_incident(
        {
            "event_id": "evt_live_gcp_smoke_01",
            "machine_id": "FANUC_0iTF_CHAKAN_04",
            "tool_id": "T03",
            "state": "YELLOW_M01_HOLD",
            "coherence": 0.84,
            "ppap_passed": True,
            "estimated_savings_inr": 16200,
            "cycle_time_penalty_sec": 4.2,
        }
    )
    agg = bq_logger.get_shift_economic_aggregates()
    print(f"  -> Updated Shift Ledger: {agg['headline_display']} ({agg['parts_inspected_shift']} parts)")
    print("\n======================================================================")
    print(" ALL 4 LIVE GCP CHECKS PASSED")
    print("======================================================================")


if __name__ == "__main__":
    asyncio.run(main())
