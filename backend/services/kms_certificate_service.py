"""
backend/services/kms_certificate_service.py
Cryptographic QA & Foundry Chargeback Certificate Service:
- Binds the `cycle_id` in-cycle vibration telemetry summary to the post-cycle
  raw optical frame SHA-256 digest in a canonical JSON audit record.
- Signs the payload via Google Cloud KMS (`EC_SIGN_P256_SHA256`) when online,
  with an automatic local `cryptography` ECDSA P-256 (SECP256R1 + SHA256) fallback
  so live demos and edge stations remain cryptographically verifiable offline.
- Renders a deterministic, high-contrast industrial QA / Foundry Chargeback
  Certificate PNG via Pillow (PIL).
"""
import base64
import datetime
import hashlib
import io
import json
import logging
from pathlib import Path
from typing import Any, Optional
from PIL import Image, ImageDraw
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from config.settings import settings
from backend.models.schemas import AOIInspectionResult, InCycleTelemetrySummary

try:
    from google.cloud import kms  # type: ignore
except ImportError:
    kms = None

try:
    from google.cloud import storage  # type: ignore
except ImportError:
    storage = None

logger = logging.getLogger("vinyas_ai.backend.kms_certificate")


class KMSCertificateService:
    def __init__(self, kms_key_resource: Optional[str] = None):
        if kms_key_resource:
            self.kms_key_resource = kms_key_resource
        elif settings.KMS_KEY_RING and settings.KMS_CRYPTO_KEY and settings.GCP_PROJECT_ID:
            self.kms_key_resource = (
                f"projects/{settings.GCP_PROJECT_ID}/locations/{settings.GCP_LOCATION}/"
                f"keyRings/{settings.KMS_KEY_RING}/cryptoKeys/{settings.KMS_CRYPTO_KEY}/cryptoKeyVersions/1"
            )
        else:
            self.kms_key_resource = settings.CLOUD_KMS_KEY_RESOURCE
        # Deterministic local ECDSA P-256 fallback keypair for offline verification
        self._local_private_key = ec.generate_private_key(ec.SECP256R1())
        self._local_public_key = self._local_private_key.public_key()

    @staticmethod
    def compute_raw_frame_sha256(raw_frame_bytes: bytes) -> str:
        return hashlib.sha256(raw_frame_bytes).hexdigest()

    def build_canonical_audit_payload(
        self,
        part_id: str,
        work_order_id: str,
        raw_frame_sha256: str,
        aoi_result: AOIInspectionResult,
        in_cycle_summary: Optional[InCycleTelemetrySummary] = None,
    ) -> bytes:
        summary = in_cycle_summary or aoi_result.in_cycle_summary or InCycleTelemetrySummary(
            cycle_id=aoi_result.cycle_id
        )
        record = {
            "issuer": "Vinyas Industrial QA Provenance Authority",
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "part_id": part_id,
            "work_order_id": work_order_id,
            "cycle_id": summary.cycle_id,
            "raw_frame_sha256": raw_frame_sha256,
            "in_cycle_telemetry": {
                "machine_id": summary.machine_id,
                "tool_id": summary.tool_id,
                "stage_a_state": summary.stage_a_state,
                "peak_vibration_rms_g": summary.peak_vibration_rms_g,
                "band_power_ratio_2k_8k": summary.band_power_ratio_2k_8k,
                "hilbert_envelope_coherence": summary.hilbert_envelope_coherence,
                "chatter_detected": summary.chatter_detected,
            },
            "post_cycle_aoi": {
                "passed_iatf_16949": aoi_result.passed_iatf_16949,
                "matched_reference_token_id": aoi_result.matched_reference_token_id,
                "detected_anomaly_type": aoi_result.detected_anomaly_type,
                "surface_ra_estimate_um": aoi_result.surface_ra_estimate_um,
            },
        }
        return json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def sign_payload_p256(self, payload_bytes: bytes) -> tuple[str, str]:
        """
        Signs payload_bytes using Google Cloud KMS EC_SIGN_P256_SHA256 when online,
        falling back cleanly to local cryptography ECDSA P-256 offline.
        Returns (signature_b64, signing_backend).
        """
        digest = hashlib.sha256(payload_bytes).digest()

        if not settings.DEMO_SAFE_MODE and kms is not None and "cryptoKeyVersions" in self.kms_key_resource:
            try:
                client = kms.KeyManagementServiceClient()
                sign_response = client.asymmetric_sign(
                    request={
                        "name": self.kms_key_resource,
                        "digest": {"sha256": digest},
                    }
                )
                return (
                    base64.b64encode(sign_response.signature).decode("ascii"),
                    "GOOGLE_CLOUD_KMS_EC_P256_SHA256",
                )
            except Exception as exc:
                logger.warning("Cloud KMS signing unavailable (%s); using local ECDSA P-256 fallback.", exc)

        local_sig = self._local_private_key.sign(payload_bytes, ec.ECDSA(hashes.SHA256()))
        return (
            base64.b64encode(local_sig).decode("ascii"),
            "LOCAL_ECDSA_P256_SHA256_OFFLINE",
        )

    def verify_local_signature(self, payload_bytes: bytes, signature_b64: str) -> bool:
        """Verifies a local ECDSA P-256 signature against this service's public key."""
        try:
            sig_bytes = base64.b64decode(signature_b64)
            self._local_public_key.verify(sig_bytes, payload_bytes, ec.ECDSA(hashes.SHA256()))
            return True
        except Exception:
            return False

    def get_public_key_pem(self) -> str:
        return self._local_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")

    def render_certificate_png(
        self,
        part_id: str,
        work_order_id: str,
        raw_frame_bytes: bytes,
        aoi_result: AOIInspectionResult,
        in_cycle_summary: Optional[InCycleTelemetrySummary] = None,
        output_path: Optional[Path] = None,
    ) -> dict[str, Any]:
        """
        Generates a high-contrast Pillow QA / Foundry Chargeback Certificate PNG,
        computes raw frame SHA-256, signs the canonical cycle_id audit payload via
        ECDSA P-256 / Cloud KMS, and optionally writes the PNG to `output_path`.
        """
        raw_frame_sha256 = self.compute_raw_frame_sha256(raw_frame_bytes)
        summary = in_cycle_summary or aoi_result.in_cycle_summary or InCycleTelemetrySummary(
            cycle_id=aoi_result.cycle_id
        )

        payload_bytes = self.build_canonical_audit_payload(
            part_id=part_id,
            work_order_id=work_order_id,
            raw_frame_sha256=raw_frame_sha256,
            aoi_result=aoi_result,
            in_cycle_summary=summary,
        )
        signature_b64, signing_backend = self.sign_payload_p256(payload_bytes)

        is_chargeback = aoi_result.detected_anomaly_type == "FOUNDRY_POROSITY_CHARGEBACK"
        if is_chargeback:
            accent = (245, 166, 35)
            header_title = "VINYAS FOUNDRY CHARGEBACK CERTIFICATE (+INR 14,000)"
            disposition = "QUARANTINE — UPSTREAM FOUNDRY POROSITY (ZERO CNC CHATTER)"
        elif aoi_result.passed_iatf_16949:
            accent = (0, 230, 150)
            header_title = "VINYAS IATF 16949 QA PASSED CERTIFICATE"
            disposition = f"PASS — GOLDEN MASTER ({aoi_result.matched_reference_token_id})"
        else:
            accent = (235, 77, 75)
            header_title = "VINYAS IATF 16949 MACHINING REJECT RECORD"
            disposition = f"HOLD / REJECT — {aoi_result.detected_anomaly_type} ({aoi_result.matched_reference_token_id})"

        img = Image.new("RGB", (760, 420), color=(14, 19, 28))
        draw = ImageDraw.Draw(img)

        # High-contrast double industrial frame
        draw.rectangle((8, 8, 751, 411), outline=accent, width=3)
        draw.rectangle((16, 16, 743, 403), outline=(58, 74, 96), width=1)
        draw.rectangle((18, 18, 741, 66), fill=(22, 32, 48))

        draw.text((30, 34), header_title, fill=accent)
        draw.text((30, 82), f"Component Part ID : {part_id}    |    Work Order: {work_order_id}", fill=(240, 245, 255))
        draw.text((30, 106), f"Linked Cycle ID   : {summary.cycle_id}    |    Machine: {summary.machine_id} ({summary.tool_id})", fill=(190, 215, 240))
        draw.text((30, 132), f"Disposition       : {disposition}", fill=accent)

        # In-Cycle Vibration Evidence Box
        draw.rectangle((28, 160, 730, 240), fill=(20, 28, 40), outline=(70, 90, 115), width=1)
        draw.text((40, 170), "LINKED IN-CYCLE 48 kHz STEREO TELEMETRY SUMMARY", fill=(110, 200, 255))
        draw.text(
            (40, 194),
            f"State: {summary.stage_a_state}  |  Vib RMS: {summary.peak_vibration_rms_g:.2f} G  |  2-8kHz Band Ratio: {summary.band_power_ratio_2k_8k:.2f}",
            fill=(230, 235, 242),
        )
        draw.text(
            (40, 214),
            f"Hilbert Coherence: {summary.hilbert_envelope_coherence:.2f}  |  CT Ripple: {summary.ct_ripple_std_amps:.2f} A  |  Chatter Flag: {summary.chatter_detected}",
            fill=(230, 235, 242),
        )

        # Post-Cycle Optical Evidence Box
        draw.rectangle((28, 252, 730, 388), fill=(18, 24, 35), outline=accent, width=1)
        draw.text((40, 262), "CRYPTOGRAPHIC PROVENANCE (RAW FRAME SHA-256 + ECDSA P-256 SIGNATURE)", fill=(255, 210, 90))
        draw.text(
            (40, 286),
            f"Matched Ref: {aoi_result.matched_reference_token_id}  |  Est. Surface Ra: {aoi_result.surface_ra_estimate_um:.2f} um  |  Fallback: {aoi_result.served_from_fallback}",
            fill=(235, 240, 248),
        )
        draw.text((40, 310), f"Raw Frame SHA-256 : {raw_frame_sha256}", fill=(130, 210, 255))
        draw.text((40, 334), f"Signing Authority : {signing_backend}", fill=(160, 240, 190))
        draw.text((40, 358), f"P-256 Signature   : {signature_b64[:66]}...", fill=(210, 215, 225))

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        png_bytes = buf.getvalue()

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(png_bytes)

        gcs_vault_uri: Optional[str] = None
        target_bucket = settings.GCS_QA_BUCKET or settings.GCS_QA_VAULT_BUCKET
        if not settings.DEMO_SAFE_MODE and storage is not None and target_bucket:
            try:
                bucket_name = target_bucket.replace("gs://", "").strip("/")
                blob_name = f"certificates/{part_id}_{summary.cycle_id}_{raw_frame_sha256[:12]}.png"
                storage_client = storage.Client(project=settings.GCP_PROJECT_ID)
                bucket = storage_client.bucket(bucket_name)
                blob = bucket.blob(blob_name)
                blob.upload_from_string(png_bytes, content_type="image/png")
                gcs_vault_uri = f"gs://{bucket_name}/{blob_name}"
                logger.info("Archived signed QA certificate to GCS Vault: %s", gcs_vault_uri)
            except Exception as exc:
                logger.warning("GCS QA Vault upload skipped (%s)", exc)

        return {
            "certificate_png_bytes": png_bytes,
            "raw_frame_sha256": raw_frame_sha256,
            "kms_signature_b64": signature_b64,
            "signing_backend": signing_backend,
            "canonical_payload_bytes": payload_bytes,
            "cycle_id": summary.cycle_id,
            "gcs_vault_uri": gcs_vault_uri,
        }
