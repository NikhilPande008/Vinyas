"""Dataset builder & blind-draw loader for Mock Rig v2 (`backend/mock_rig/dataset.py`).

Generates 60 seeded samples (20 per line: ~50% nominal, ~35% true defect, ~15% hard negative).
Ground-truth labels are stored ONLY in `data/mock_rig/manifest.json`.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Literal, Optional

import numpy as np
from PIL import Image

from backend.config import PROJECT_ROOT
from backend.mock_rig.images import (
    generate_cnc_part_image,
    generate_pcb_image,
    generate_weld_image,
)
from backend.mock_rig.process import generate_pcb_telemetry, generate_weld_telemetry
from backend.mock_rig.vibration import generate_cnc_vibration


MOCK_RIG_DIR = PROJECT_ROOT / "data" / "mock_rig"
SAMPLES_DIR = MOCK_RIG_DIR / "samples"
MANIFEST_PATH = MOCK_RIG_DIR / "manifest.json"

LINE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "PCB": {
        "line": "PCB",
        "line_name": "Line A — Automotive SMT PCB Reflow",
        "machine_id": "SMT-REFLOW-CHAKAN-A1",
        "part_sku": "ECU-BMS-QFP64-REV4",
        "modality": "Optical camera + reflow process telemetry",
        "has_audio": False,
        "note": "Simulated camera frame and SAC305 reflow telemetry.",
    },
    "CNC": {
        "line": "CNC",
        "line_name": "Line B — High-Speed CNC Spindle",
        "machine_id": "CNC-SPINDLE-CHAKAN-B2",
        "part_sku": "SPINDLE-7014C-P4S",
        "modality": "48 kHz vibration signal + machined part frame",
        "has_audio": True,
        "note": "Bearing sits inside the assembled spindle; CNC decision is vibration-led (envelope DSP).",
    },
    "WELD": {
        "line": "WELD",
        "line_name": "Line C — Robotic MIG Chassis Weld",
        "machine_id": "MIG-ARC-BHOSARI-C3",
        "part_sku": "SUBFRAME-MIG-220-LH",
        "modality": "Optical weld seam frame + shielding gas & arc telemetry",
        "has_audio": False,
        "note": "Simulated weld seam frame and 82% Ar / 18% CO2 MIG telemetry.",
    },
}

# 20 samples per line: 10 nominal (50%), 7 true defects (35%), 3 hard negatives (15%)
_LINE_SPECS: dict[str, list[tuple[str, bool, str]]] = {
    "PCB": (
        [("NOMINAL", False, "none")] * 10
        + [("SOLDER_BRIDGE", True, "severe")] * 4
        + [("INSUFFICIENT_SOLDER", True, "mild")] * 3
        + [("FLUX_RESIDUE_GLARE", False, "none")] * 3
    ),
    "CNC": (
        [("NOMINAL", False, "none")] * 10
        + [("OUTER_RACE_FAULT", True, "severe")] * 4
        + [("OUTER_RACE_FAULT", True, "mild")] * 2
        + [("IMBALANCE", True, "mild")] * 1
        + [("WRENCH_STRIKE", False, "none")] * 3
    ),
    "WELD": (
        [("NOMINAL", False, "none")] * 10
        + [("POROSITY_GAS_LOSS", True, "severe")] * 4
        + [("POROSITY_GAS_LOSS", True, "mild")] * 3
        + [("SPATTER_COSMETIC", False, "none")] * 3
    ),
}


def build_dataset(seed: int = 2026, force: bool = False) -> list[dict[str, Any]]:
    """Build deterministic 60-sample dataset with hidden ground-truth manifest."""
    if not force and MANIFEST_PATH.is_file():
        existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if len(existing) >= 60:
            return existing

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    master_rng = np.random.default_rng(seed)
    manifest: list[dict[str, Any]] = []

    for line, specs in _LINE_SPECS.items():
        # Shuffle order deterministically so sample IDs don't leak class
        order = list(range(len(specs)))
        master_rng.shuffle(order)

        for seq_idx, spec_idx in enumerate(order, start=1):
            defect_type, is_defect, severity = specs[spec_idx]
            sample_seed = int(master_rng.integers(1, 2_000_000_000))
            rng = np.random.default_rng(sample_seed)
            sample_id = f"{line}-{seq_idx:04d}"
            sample_dir = SAMPLES_DIR / sample_id
            sample_dir.mkdir(parents=True, exist_ok=True)

            gt_bbox: Optional[list[int]] = None
            has_wav = False

            if line == "PCB":
                png_bytes, gt_bbox = generate_pcb_image(defect_type, rng)
                telemetry = generate_pcb_telemetry(defect_type, rng)
            elif line == "CNC":
                vib = generate_cnc_vibration(defect_type, severity, rng)
                (sample_dir / "vib.wav").write_bytes(vib.wav_bytes)
                has_wav = True
                png_bytes, gt_bbox = generate_cnc_part_image(rng)
                telemetry = {
                    "vibration_khz": round(vib.bpfo_hz / 1000.0, 3),
                    "vibration_rms_mms": vib.rms_velocity_mms,
                    "temperature_c": vib.spindle_temp_c,
                    "line_speed_rpm": vib.rpm,
                    "shielding_gas_lpm": None,
                }
            else:  # WELD
                png_bytes, gt_bbox = generate_weld_image(defect_type, rng)
                telemetry = generate_weld_telemetry(defect_type, rng)

            (sample_dir / "frame.png").write_bytes(png_bytes)
            public_meta = {
                "sample_id": sample_id,
                "line": line,
                "machine_id": LINE_DEFINITIONS[line]["machine_id"],
                "part_sku": LINE_DEFINITIONS[line]["part_sku"],
                "has_wav": has_wav,
                "telemetry": telemetry,
                "input_simulated": True,
            }
            (sample_dir / "telemetry.json").write_text(
                json.dumps(public_meta, indent=2), encoding="utf-8"
            )

            manifest.append(
                {
                    "sample_id": sample_id,
                    "line": line,
                    "is_defect": is_defect,
                    "label": "DEFECT" if is_defect else "NOMINAL",
                    "defect_type": defect_type,
                    "severity": severity,
                    "gt_bbox": gt_bbox,
                    "seed": sample_seed,
                }
            )

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def ensure_dataset(seed: int = 2026) -> None:
    if not MANIFEST_PATH.is_file():
        build_dataset(seed=seed, force=False)


def list_sample_ids_for_line(line: str) -> list[str]:
    """List sample IDs for a line WITHOUT reading manifest.json."""
    ensure_dataset()
    prefix = f"{line.upper()}-"
    if not SAMPLES_DIR.exists():
        return []
    return sorted(
        p.name for p in SAMPLES_DIR.iterdir() if p.is_dir() and p.name.startswith(prefix)
    )


def load_sample_public(sample_id: str) -> dict[str, Any]:
    """Load public sample telemetry & file paths WITHOUT touching manifest.json."""
    ensure_dataset()
    sample_dir = (SAMPLES_DIR / sample_id).resolve()
    if not sample_dir.is_relative_to(SAMPLES_DIR.resolve()) or not sample_dir.is_dir():
        raise FileNotFoundError(f"Sample {sample_id} not found")
    meta = json.loads((sample_dir / "telemetry.json").read_text(encoding="utf-8"))
    meta["frame_path"] = str(sample_dir / "frame.png")
    wav_path = sample_dir / "vib.wav"
    meta["wav_path"] = str(wav_path) if wav_path.is_file() else None
    return meta


def draw_random_sample(line: str, rng: Optional[random.Random] = None) -> dict[str, Any]:
    """Draw a random sample for a line (no ground-truth label returned)."""
    ids = list_sample_ids_for_line(line)
    if not ids:
        raise FileNotFoundError(f"No samples available for line {line}")
    chosen = (rng or random).choice(ids)
    return load_sample_public(chosen)


def build_contact_sheet(output_path: Path, per_line: int = 5) -> Path:
    """Save a 3x5 contact sheet of mock-rig frames for visual verification (no text)."""
    ensure_dataset()
    thumb_w, thumb_h = 256, 171
    sheet = Image.new("RGB", (thumb_w * per_line, thumb_h * 3), (18, 22, 28))
    for row_idx, line in enumerate(["PCB", "CNC", "WELD"]):
        ids = list_sample_ids_for_line(line)[:per_line]
        for col_idx, sid in enumerate(ids):
            im = Image.open(SAMPLES_DIR / sid / "frame.png").resize((thumb_w, thumb_h), Image.BICUBIC)
            sheet.paste(im, (col_idx * thumb_w, row_idx * thumb_h))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="PNG")
    return output_path
