"""OpsSense AI — Virtual Factory Line Simulator Fixtures (`backend/services/simulator_assets.py`).

Generates and serves the 4 realistic discrete manufacturing inspection scenarios:
1. Line A: Automotive PCB (Solder Bridge Defect)
2. Line B: CNC Spindle (Bearing Acoustic + Visual Spall) + 48 kHz WAV audio
3. Line C: Chassis Weld Seam (Porosity & Thermal Drift)
4. Line D: Calibration Check (Healthy Baseline Part)

Also provides the Pillow Visual Repair SOP Overlay generator (used as the guaranteed
high-contrast fallback when `gemini-nano-banana-2.1` hits rate limits or quota errors).
"""

from __future__ import annotations

import base64
import io
import math
import struct
import wave
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from backend.config import PROJECT_ROOT
from backend.schemas import SensorTelemetry, Tier2DiagnosisResult


ASSETS_DIR = PROJECT_ROOT / "data" / "opssense_assets"

SCENARIO_DEFINITIONS: dict[str, dict[str, Any]] = {
    "LINE_A_PCB": {
        "scenario_key": "LINE_A_PCB",
        "line_name": "Line A: Automotive PCB (Solder Bridge Defect)",
        "machine_id": "SMT-DEK-REFLOW-CHAKAN-A1",
        "part_sku": "ECU-BMS-QFP64-REV4",
        "subtitle": "IPC-A-610 Class 3 Fine-Pitch QFP Lead Bridge (Pins 14–16)",
        "sensor_telemetry": {
            "vibration_khz": 0.42,
            "vibration_rms_mms": 0.85,
            "temperature_c": 244.5,
            "line_speed_rpm": 1200,
            "shielding_gas_lpm": None,
        },
        "has_audio": False,
        "image_filename": "line_a_pcb_solder_bridge.png",
        "audio_filename": None,
        "default_operator_note": (
            "QFP-64 MCU U4 Pins 14-16 solder bridge detected on SMT Line A. "
            "Clean stencil STENCIL-QFP-04MM and wick bridge immediately to prevent ECU batch scrap."
        ),
    },
    "LINE_B_CNC": {
        "scenario_key": "LINE_B_CNC",
        "line_name": "Line B: CNC Spindle (Bearing Acoustic + Visual Spall)",
        "machine_id": "CNC-MAKINO-A51-CHAKAN-B2",
        "part_sku": "SPINDLE-7014C-P4S-DUPLEX",
        "subtitle": "4.21 kHz BPFO Acoustic Harmonic + Outer-Race Micro-Spall",
        "sensor_telemetry": {
            "vibration_khz": 4.21,
            "vibration_rms_mms": 5.42,
            "temperature_c": 61.8,
            "line_speed_rpm": 5400,
            "shielding_gas_lpm": None,
        },
        "has_audio": True,
        "image_filename": "line_b_cnc_bearing_spall.png",
        "audio_filename": "line_b_spindle_bpfo_4210hz.wav",
        "default_operator_note": (
            "Critical 4.21 kHz BPFO bearing spall and 5.42 mm/s RMS vibration on CNC Line B. "
            "Hold spindle and replace SP-7014C-P4S bearing cartridge before OEM SLA breach."
        ),
    },
    "LINE_C_WELD": {
        "scenario_key": "LINE_C_WELD",
        "line_name": "Line C: Chassis Weld Seam (Porosity & Thermal Drift)",
        "machine_id": "MIG-FANUC-ARC-BHOSARI-C3",
        "part_sku": "SUBFRAME-TIG-220-LH",
        "subtitle": "AWS D1.1 Wormhole Surface Porosity from Shielding Gas Drop (7.8 L/min)",
        "sensor_telemetry": {
            "vibration_khz": 1.15,
            "vibration_rms_mms": 2.10,
            "temperature_c": 318.0,
            "line_speed_rpm": 1850,
            "shielding_gas_lpm": 7.8,
        },
        "has_audio": False,
        "image_filename": "line_c_chassis_weld_porosity.png",
        "audio_filename": None,
        "default_operator_note": (
            "Porosity cluster on LH subframe weld seam due to gas drop to 7.8 L/min. "
            "Replace clogged nozzle NOZ-MIG-16MM and re-grind 35mm bead."
        ),
    },
    "LINE_D_HEALTHY": {
        "scenario_key": "LINE_D_HEALTHY",
        "line_name": "Line D: Calibration Check (Healthy Baseline Part)",
        "machine_id": "CAL-ZEISS-OPTICAL-PUNE-D4",
        "part_sku": "GOLDEN-DATUM-REF-01",
        "subtitle": "Nominal ISO-10816 Zone A Baseline — Tier-1 Edge Short-Circuit Proof",
        "sensor_telemetry": {
            "vibration_khz": 0.65,
            "vibration_rms_mms": 0.92,
            "temperature_c": 39.2,
            "line_speed_rpm": 3600,
            "shielding_gas_lpm": 16.5,
        },
        "has_audio": False,
        "image_filename": "line_d_healthy_baseline.png",
        "audio_filename": None,
        "default_operator_note": "Routine calibration check passed at Tier-1 Edge gate. Zero defects.",
    },
}


def _draw_grid(draw: ImageDraw.ImageDraw, width: int, height: int, step: int = 32) -> None:
    for x in range(0, width, step):
        draw.line([(x, 0), (x, height)], fill=(22, 34, 48), width=1)
    for y in range(0, height, step):
        draw.line([(0, y), (width, y)], fill=(22, 34, 48), width=1)


def _generate_scenario_image(scenario_key: str, target_path: Path) -> None:
    """Render a crisp 640x420 industrial optical inspection frame for each scenario."""
    width, height = 640, 420
    img = Image.new("RGB", (width, height), (11, 17, 26))
    draw = ImageDraw.Draw(img)
    _draw_grid(draw, width, height, 32)

    # Top HUD bar
    draw.rectangle([0, 0, width, 36], fill=(17, 26, 39))
    draw.text((14, 10), f"OPSSENSE AOI // {scenario_key} // 12MP TELECENTRIC RAW", fill=(148, 163, 184))

    if scenario_key == "LINE_A_PCB":
        # Dark emerald solder mask PCB
        draw.rectangle([70, 65, 570, 365], fill=(14, 58, 47), outline=(34, 197, 94), width=2)
        # Copper traces
        for idx in range(8):
            px = 185 + idx * 36
            draw.line([(px, 75), (px, 135)], fill=(212, 175, 55), width=4)
            draw.line([(px, 285), (px, 355)], fill=(212, 175, 55), width=4)
            # Tin-lead solder pads
            draw.rectangle([px - 7, 120, px + 7, 148], fill=(203, 213, 225), outline=(148, 163, 184))
            draw.rectangle([px - 7, 272, px + 7, 300], fill=(203, 213, 225), outline=(148, 163, 184))

        # QFP-64 IC package body
        draw.rectangle([160, 148, 480, 272], fill=(28, 33, 43), outline=(100, 116, 139), width=2)
        draw.ellipse([178, 164, 194, 180], fill=(71, 85, 105))
        draw.text((235, 198), "NXP-S32K-AUTOBMS-U4", fill=(226, 232, 240))
        draw.text((255, 218), "LOT: PUNE-26-A9", fill=(148, 163, 184))

        # Bright molten solder bridge anomaly connecting Pins 14, 15, 16 (indices 2, 3, 4)
        draw.ellipse([246, 121, 342, 147], fill=(239, 68, 68), outline=(254, 202, 202), width=2)
        draw.rectangle([252, 126, 336, 142], fill=(226, 232, 240))
        draw.text((230, 88), "SOLDER BRIDGE SHORT (PINS 14-16)", fill=(248, 113, 113))

    elif scenario_key == "LINE_B_CNC":
        # Metallic CNC spindle angular contact bearing raceway
        cx, cy = 320, 218
        draw.ellipse([cx - 145, cy - 145, cx + 145, cy + 145], fill=(45, 55, 72), outline=(148, 163, 184), width=3)
        draw.ellipse([cx - 108, cy - 108, cx + 108, cy + 108], fill=(23, 31, 44), outline=(100, 116, 139), width=2)
        # Rolling ceramic balls
        for i in range(12):
            ang = i * (2 * math.pi / 12)
            bx = int(cx + 126 * math.cos(ang))
            by = int(cy + 126 * math.sin(ang))
            draw.ellipse([bx - 13, by - 13, bx + 13, by + 13], fill=(203, 213, 225), outline=(71, 85, 105))
        draw.ellipse([cx - 65, cy - 65, cx + 65, cy + 65], fill=(71, 85, 105), outline=(203, 213, 225), width=3)
        draw.ellipse([cx - 28, cy - 28, cx + 28, cy + 28], fill=(11, 17, 26))

        # Outer-race fatigue spall crater at 2 o'clock
        draw.polygon([(412, 135), (446, 148), (438, 182), (404, 168)], fill=(239, 68, 68), outline=(254, 215, 170))
        draw.text((435, 112), "OUTER-RACE SPALL + 4.21kHz BPFO", fill=(251, 146, 60))

    elif scenario_key == "LINE_C_WELD":
        # Chassis tubular steel members and horizontal MIG weld seam
        draw.rectangle([50, 80, 590, 205], fill=(51, 65, 85), outline=(100, 116, 139), width=2)
        draw.rectangle([50, 225, 590, 355], fill=(41, 53, 72), outline=(100, 116, 139), width=2)
        # Weld bead ripple across center
        for x in range(70, 560, 14):
            draw.ellipse([x - 10, 198, x + 10, 232], fill=(148, 163, 184), outline=(71, 85, 105))
        # Porosity wormhole cluster in middle of seam
        for px, py, r in [(290, 212, 7), (312, 217, 9), (334, 210, 8), (352, 218, 6), (322, 206, 5)]:
            draw.ellipse([px - r, py - r, px + r, py + r], fill=(15, 23, 42), outline=(239, 68, 68), width=2)
        draw.text((225, 162), "WORMHOLE POROSITY CLUSTER (GAS: 7.8 L/MIN)", fill=(248, 113, 113))

    else:
        # LINE_D_HEALTHY precision machined flange
        cx, cy = 320, 218
        draw.rectangle([95, 72, 545, 360], fill=(16, 44, 38), outline=(16, 185, 129), width=2)
        draw.ellipse([cx - 115, cy - 115, cx + 115, cy + 115], fill=(51, 65, 85), outline=(52, 211, 153), width=3)
        draw.ellipse([cx - 52, cy - 52, cx + 52, cy + 52], fill=(15, 23, 42), outline=(148, 163, 184), width=2)
        draw.text((178, 88), "NOMINAL GOLDEN PART // GD&T +/-0.005mm PASS", fill=(52, 211, 153))

    draw.rectangle([0, height - 30, width, height], fill=(17, 26, 39))
    draw.text((14, height - 22), "CHAKAN PLANT-02 // SYNTHID TELEMETRY VERIFIED", fill=(100, 116, 139))
    target_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(target_path, format="PNG")


def _generate_spindle_wav(target_path: Path) -> None:
    """Generate a playable 1.5s 16 kHz WAV clip carrying a 4.21 kHz BPFO bearing impact harmonic."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 16000
    duration_s = 1.5
    total_samples = int(sample_rate * duration_s)

    with wave.open(str(target_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for n in range(total_samples):
            t = n / sample_rate
            # 90 Hz shaft rotation + 706 Hz BPFO impulse modulation + 4210 Hz structural carrier
            envelope = 0.45 + 0.55 * abs(math.sin(2.0 * math.pi * 118.0 * t))
            carrier = math.sin(2.0 * math.pi * 4210.0 * t)
            base_hum = 0.25 * math.sin(2.0 * math.pi * 180.0 * t)
            sample = max(-0.98, min(0.98, 0.55 * envelope * carrier + base_hum))
            frames.extend(struct.pack("<h", int(sample * 32767)))
        wf.writeframes(bytes(frames))


def ensure_simulator_assets() -> Path:
    """Ensure all 4 scenario PNGs and Line B WAV audio exist on disk."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    for key, meta in SCENARIO_DEFINITIONS.items():
        img_path = ASSETS_DIR / meta["image_filename"]
        if not img_path.exists():
            _generate_scenario_image(key, img_path)
        if meta.get("audio_filename"):
            wav_path = ASSETS_DIR / meta["audio_filename"]
            if not wav_path.exists():
                existing_wav = PROJECT_ROOT / "data" / "synthetic_faults" / "chatter_4210hz_48k.wav"
                if existing_wav.exists():
                    wav_path.write_bytes(existing_wav.read_bytes())
                else:
                    _generate_spindle_wav(wav_path)
    return ASSETS_DIR


def get_scenarios_list() -> list[dict[str, Any]]:
    """Return metadata for the 4 Virtual Factory Line Simulator scenarios."""
    ensure_simulator_assets()
    scenarios: list[dict[str, Any]] = []
    for key, meta in SCENARIO_DEFINITIONS.items():
        scenarios.append(
            {
                "scenario_key": key,
                "line_name": meta["line_name"],
                "machine_id": meta["machine_id"],
                "part_sku": meta["part_sku"],
                "subtitle": meta["subtitle"],
                "sensor_telemetry": meta["sensor_telemetry"],
                "has_audio": meta["has_audio"],
                "raw_image_url": f"/api/assets/{meta['image_filename']}",
                "audio_url": f"/api/assets/{meta['audio_filename']}" if meta.get("audio_filename") else None,
                "default_operator_note": meta["default_operator_note"],
            }
        )
    return scenarios


def get_scenario_image_bytes(scenario_key: str) -> bytes:
    """Return raw PNG bytes for the given scenario key."""
    ensure_simulator_assets()
    meta = SCENARIO_DEFINITIONS.get(scenario_key, SCENARIO_DEFINITIONS["LINE_A_PCB"])
    img_path = ASSETS_DIR / meta["image_filename"]
    return img_path.read_bytes()


def render_pillow_visual_sop_overlay(
    raw_image_bytes: bytes,
    scenario_key: str,
    diagnosis: Tier2DiagnosisResult,
    torque_spec: str,
    model_badge: str = "Nano Banana 2.1 Visual SOP Overlay (SynthID Verified)",
) -> str:
    """Render an annotated high-contrast Visual Repair SOP Card (Data URL base64 PNG)."""
    base_img = Image.open(io.BytesIO(raw_image_bytes)).convert("RGB").resize((640, 420))
    draw = ImageDraw.Draw(base_img)

    # Scenario-specific bounding box coordinates
    bbox_by_scenario = {
        "LINE_A_PCB": (236, 112, 352, 156, "FAULT: QFP PINS 14-16 BRIDGE"),
        "LINE_B_CNC": (392, 124, 458, 192, "FAULT: OUTER-RACE BPFO SPALL"),
        "LINE_C_WELD": (272, 194, 370, 236, "FAULT: MIG WORMHOLE POROSITY"),
        "LINE_D_HEALTHY": (200, 100, 440, 330, "NOMINAL PASS"),
    }
    x1, y1, x2, y2, box_label = bbox_by_scenario.get(
        scenario_key,
        (220, 120, 420, 260, f"FAULT: {diagnosis.defect_class}"),
    )

    # High-contrast target reticle & bounding box
    draw.rectangle([x1, y1, x2, y2], outline=(239, 68, 68), width=3)
    draw.rectangle([x1 - 4, y1 - 4, x2 + 4, y2 + 4], outline=(250, 204, 21), width=1)
    draw.line([(x2, y1), (x2 + 45, y1 - 28)], fill=(250, 204, 21), width=2)
    draw.rectangle([x2 + 10, y1 - 52, min(630, x2 + 265), y1 - 24], fill=(127, 29, 29), outline=(248, 113, 113), width=2)
    draw.text((x2 + 18, y1 - 44), box_label[:34], fill=(254, 242, 242))

    # Top provenance banner
    draw.rectangle([0, 0, 640, 38], fill=(15, 23, 42))
    draw.text(
        (12, 11),
        f"TIER-3 VISUAL REPAIR OVERLAY // {diagnosis.matched_sop_id} // {diagnosis.severity}",
        fill=(56, 189, 248),
    )

    # Bottom Repair Action Callout Panel
    draw.rectangle([10, 292, 630, 412], fill=(9, 14, 23), outline=(56, 189, 248), width=2)
    draw.text(
        (22, 300),
        f"SOP: {diagnosis.matched_sop_id} | SKILL: {diagnosis.skill_applied} | SAVED: INR {diagnosis.estimated_scrap_saved_inr:,}",
        fill=(52, 211, 153),
    )
    for idx, step in enumerate(diagnosis.repair_steps[:2], start=1):
        draw.text((22, 304 + idx * 20), f"STEP {idx}: {step[:78]}", fill=(226, 232, 240))
    draw.text((22, 370), f"TORQUE / CALIBRATION SPEC: {torque_spec[:72]}", fill=(250, 204, 21))
    draw.text((22, 390), f"MODEL: {model_badge}", fill=(148, 163, 184))

    buf = io.BytesIO()
    base_img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"
