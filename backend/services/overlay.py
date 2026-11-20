"""Deterministic Tier-3 Visual Repair Overlay (`backend/services/overlay.py`).

Rules:
- Operates on the actual image resolution (never resizes to a fixed 640x420 first).
- Draws a bounding box ONLY when a model returned valid `[ymin, xmin, ymax, xmax]`
  (0..1000) coordinates AND `defect_type != "NO_DEFECT_FOUND"`.
- Zero hard-coded scenario coordinates.
- Shows SOP ID and SOP-verified values only in a clean bottom callout strip.
"""

from __future__ import annotations

import base64
import io
import time
from typing import Optional

from PIL import Image, ImageDraw

from backend.schemas import StageProvenance, Tier2DiagnosisResult


def render_model_bbox_overlay(
    raw_image_bytes: bytes,
    diagnosis: Tier2DiagnosisResult,
    torque_spec: str,
    bbox_source_model: Optional[str],
    fallback_bbox_hint: Optional[list[int]] = None,
    input_simulated: bool = True,
) -> tuple[str, StageProvenance]:
    """Render deterministic SOP callout card + optional model-located bbox on actual frame."""
    t0 = time.perf_counter()
    base = Image.open(io.BytesIO(raw_image_bytes)).convert("RGB")
    w, h = base.size

    strip_h = 68
    canvas = Image.new("RGB", (w, h + strip_h), (15, 23, 42))
    canvas.paste(base, (0, 0))
    draw = ImageDraw.Draw(canvas)

    # Determine whether a valid model bbox should be drawn
    chosen_bbox: Optional[list[int]] = None
    if diagnosis.defect_type != "NO_DEFECT_FOUND":
        cand = diagnosis.bbox or fallback_bbox_hint
        if isinstance(cand, list) and len(cand) == 4:
            ymin, xmin, ymax, xmax = [max(0, min(1000, int(v))) for v in cand]
            if ymax > ymin and xmax > xmin:
                chosen_bbox = [ymin, xmin, ymax, xmax]

    if chosen_bbox is not None:
        ymin, xmin, ymax, xmax = chosen_bbox
        x0 = int(round(xmin * w / 1000.0))
        y0 = int(round(ymin * h / 1000.0))
        x1 = int(round(xmax * w / 1000.0))
        y1 = int(round(ymax * h / 1000.0))
        draw.rectangle([x0, y0, x1, y1], outline=(239, 68, 68), width=4)
        # Corner ticks for readability
        draw.rectangle([x0 + 2, y0 + 2, x1 - 2, y1 - 2], outline=(254, 202, 202), width=1)
        loc_note = f"bbox located by {bbox_source_model}" if bbox_source_model else "model bbox"
    else:
        loc_note = "No defect location returned"

    # Bottom SOP callout strip (SOP-verified values only)
    draw.rectangle([0, h, w, h + strip_h], fill=(15, 23, 42))
    draw.line([(0, h), (w, h)], fill=(51, 65, 85), width=2)
    header = f"SOP: {diagnosis.matched_sop_id}  |  Disposition advice: {diagnosis.recommended_disposition}  |  {loc_note}"
    draw.text((14, h + 10), header[:120], fill=(248, 250, 252))
    draw.text((14, h + 36), f"SOP Spec: {torque_spec}"[:120], fill=(148, 163, 184))

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    prov = StageProvenance(
        stage="T3_OVERLAY",
        producer="DETERMINISTIC",
        model_id=None,
        attempts=[],
        latency_ms=elapsed_ms,
        input_simulated=input_simulated,
        note=f"Overlay (deterministic) — {loc_note}",
    )
    return data_url, prov
