"""Procedural 768x512 inspection image generator for Mock Rig v2.

STRICT RULE: ZERO TEXT anywhere in any generated image. No defect names, no scenario
keys, no watermarks, no footers. Only physically plausible visual geometry, lighting
gradients, and texture noise.
"""

from __future__ import annotations

import io
import math
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


IMG_W = 768
IMG_H = 512


def _add_lighting_and_sensor_noise(img: Image.Image, rng: np.random.Generator) -> Image.Image:
    """Apply subtle directional illumination gradient and camera sensor noise."""
    arr = np.asarray(img, dtype=np.float32)
    yy, xx = np.mgrid[0:IMG_H, 0:IMG_W]
    gx = float(rng.uniform(-0.12, 0.12))
    gy = float(rng.uniform(-0.10, 0.10))
    grad = 1.0 + gx * ((xx - IMG_W / 2) / (IMG_W / 2)) + gy * ((yy - IMG_H / 2) / (IMG_H / 2))
    noise = rng.normal(0.0, float(rng.uniform(2.0, 4.2)), size=arr.shape).astype(np.float32)
    out = np.clip(arr * grad[..., None] + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="RGB")


def generate_pcb_image(
    defect_class: str,
    rng: np.random.Generator,
) -> tuple[bytes, Optional[list[int]]]:
    """Draw a 4-sided QFP-64 IC on green solder-mask PCB with pads, traces, and optional defect.

    Returns (png_bytes, gt_bbox_0_1000_or_None). Ground-truth bbox is stored ONLY in manifest.json.
    """
    base_g = int(rng.integers(52, 68))
    img = Image.new("RGB", (IMG_W, IMG_H), (16, base_g, 34))
    draw = ImageDraw.Draw(img)

    # Background copper traces (subtle lighter green)
    trace_col = (24, base_g + 22, 46)
    for _ in range(28):
        x0 = int(rng.integers(20, IMG_W - 20))
        y0 = int(rng.integers(20, IMG_H - 20))
        dx = int(rng.integers(-140, 140))
        dy = int(rng.integers(-90, 90))
        draw.line([(x0, y0), (x0 + dx, y0), (x0 + dx, y0 + dy)], fill=trace_col, width=3)

    # Via holes
    for _ in range(18):
        vx = int(rng.integers(40, IMG_W - 40))
        vy = int(rng.integers(40, IMG_H - 40))
        draw.ellipse([vx - 6, vy - 6, vx + 6, vy + 6], fill=(170, 145, 78))
        draw.ellipse([vx - 3, vy - 3, vx + 3, vy + 3], fill=(12, 18, 16))

    # QFP-64 centered with slight random offset
    cx = IMG_W // 2 + int(rng.integers(-28, 29))
    cy = IMG_H // 2 + int(rng.integers(-18, 19))
    body_half = 96
    leads_per_side = 16
    pitch = (2 * body_half - 24) / (leads_per_side - 1)
    pad_len = 34
    lead_len = 24

    # Silkscreen outline (shapes only, NO text)
    silk = (210, 218, 212)
    draw.rectangle(
        [cx - body_half - 44, cy - body_half - 44, cx + body_half + 44, cy + body_half + 44],
        outline=silk,
        width=2,
    )
    # Pin-1 dot on silkscreen
    draw.ellipse([cx - body_half - 34, cy - body_half - 34, cx - body_half - 22, cy - body_half - 22], fill=silk)

    # Choose defect side & pin index (random)
    defect_side = int(rng.integers(0, 4))  # 0=top, 1=bottom, 2=left, 3=right
    defect_pin = int(rng.integers(2, leads_per_side - 4))
    gt_bbox_px: Optional[list[int]] = None

    # Draw pads & leads on all 4 sides
    for side in range(4):
        for i in range(leads_per_side):
            offset = -body_half + 12 + i * pitch
            is_starved = (
                defect_class == "INSUFFICIENT_SOLDER"
                and side == defect_side
                and defect_pin <= i <= defect_pin + 2
            )
            pad_col = (88, 72, 42) if is_starved else (196, 178, 120)
            lead_col = (145, 152, 162) if is_starved else (206, 214, 224)

            if side == 0:  # top
                x = int(cx + offset)
                draw.rectangle([x - 3, cy - body_half - pad_len, x + 3, cy - body_half], fill=pad_col)
                if not is_starved:
                    draw.rectangle([x - 2, cy - body_half - lead_len, x + 2, cy - body_half], fill=lead_col)
                else:
                    draw.rectangle([x - 1, cy - body_half - 10, x + 1, cy - body_half], fill=lead_col)
            elif side == 1:  # bottom
                x = int(cx + offset)
                draw.rectangle([x - 3, cy + body_half, x + 3, cy + body_half + pad_len], fill=pad_col)
                if not is_starved:
                    draw.rectangle([x - 2, cy + body_half, x + 2, cy + body_half + lead_len], fill=lead_col)
                else:
                    draw.rectangle([x - 1, cy + body_half, x + 1, cy + body_half + 10], fill=lead_col)
            elif side == 2:  # left
                y = int(cy + offset)
                draw.rectangle([cx - body_half - pad_len, y - 3, cx - body_half, y + 3], fill=pad_col)
                if not is_starved:
                    draw.rectangle([cx - body_half - lead_len, y - 2, cx - body_half, y + 2], fill=lead_col)
                else:
                    draw.rectangle([cx - body_half - 10, y - 1, cx - body_half, y + 1], fill=lead_col)
            else:  # right
                y = int(cy + offset)
                draw.rectangle([cx + body_half, y - 3, cx + body_half + pad_len, y + 3], fill=pad_col)
                if not is_starved:
                    draw.rectangle([cx + body_half, y - 2, cx + body_half + lead_len, y + 2], fill=lead_col)
                else:
                    draw.rectangle([cx + body_half, y - 1, cx + body_half + 10, y + 1], fill=lead_col)

    # QFP black epoxy body + chamfered pin-1 bevel
    draw.rectangle(
        [cx - body_half, cy - body_half, cx + body_half, cy + body_half],
        fill=(28, 32, 38),
        outline=(62, 68, 78),
        width=3,
    )
    draw.ellipse([cx - body_half + 14, cy - body_half + 14, cx - body_half + 28, cy - body_half + 28], fill=(64, 70, 82))

    # Draw defect features
    if defect_class == "SOLDER_BRIDGE":
        p0 = -body_half + 12 + defect_pin * pitch
        p1 = -body_half + 12 + (defect_pin + 2) * pitch
        blob_col = (232, 238, 246)
        blob_edge = (162, 174, 188)
        if defect_side == 0:
            box = [int(cx + p0 - 4), cy - body_half - 28, int(cx + p1 + 4), cy - body_half - 4]
        elif defect_side == 1:
            box = [int(cx + p0 - 4), cy + body_half + 4, int(cx + p1 + 4), cy + body_half + 28]
        elif defect_side == 2:
            box = [cx - body_half - 28, int(cy + p0 - 4), cx - body_half - 4, int(cy + p1 + 4)]
        else:
            box = [cx + body_half + 4, int(cy + p0 - 4), cx + body_half + 28, int(cy + p1 + 4)]
        draw.rounded_rectangle(box, radius=7, fill=blob_col, outline=blob_edge, width=2)
        gt_bbox_px = [box[1] - 10, box[0] - 10, box[3] + 10, box[2] + 10]

    elif defect_class == "INSUFFICIENT_SOLDER":
        p0 = -body_half + 12 + defect_pin * pitch
        p1 = -body_half + 12 + (defect_pin + 2) * pitch
        if defect_side == 0:
            box = [int(cx + p0 - 8), cy - body_half - 38, int(cx + p1 + 8), cy - body_half + 4]
        elif defect_side == 1:
            box = [int(cx + p0 - 8), cy + body_half - 4, int(cx + p1 + 8), cy + body_half + 38]
        elif defect_side == 2:
            box = [cx - body_half - 38, int(cy + p0 - 8), cx - body_half + 4, int(cy + p1 + 8)]
        else:
            box = [cx + body_half - 4, int(cy + p0 - 8), cx + body_half + 38, int(cy + p1 + 8)]
        gt_bbox_px = [box[1], box[0], box[3], box[2]]

    elif defect_class == "FLUX_RESIDUE_GLARE":
        # Hard negative: translucent glossy residue patch on solder mask beside QFP (not bridging leads)
        overlay = Image.new("RGBA", (IMG_W, IMG_H), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        gx = cx + int(rng.choice([-1, 1])) * int(rng.integers(125, 185))
        gy = cy + int(rng.integers(-90, 90))
        odraw.ellipse([gx - 34, gy - 22, gx + 34, gy + 22], fill=(210, 235, 220, 62))
        odraw.ellipse([gx - 16, gy - 10, gx + 16, gy + 10], fill=(245, 255, 250, 72))
        overlay = overlay.filter(ImageFilter.GaussianBlur(radius=4))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    # Slight random rotation (-2.5 to +2.5 deg)
    angle = float(rng.uniform(-2.2, 2.2))
    img = img.rotate(angle, resample=Image.BICUBIC, fillcolor=(14, base_g - 4, 30))
    img = _add_lighting_and_sensor_noise(img, rng)

    gt_bbox_norm = None
    if gt_bbox_px is not None:
        ymin = max(0, min(1000, int(gt_bbox_px[0] * 1000 / IMG_H)))
        xmin = max(0, min(1000, int(gt_bbox_px[1] * 1000 / IMG_W)))
        ymax = max(0, min(1000, int(gt_bbox_px[2] * 1000 / IMG_H)))
        xmax = max(0, min(1000, int(gt_bbox_px[3] * 1000 / IMG_W)))
        gt_bbox_norm = [ymin, xmin, ymax, xmax]

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), gt_bbox_norm


def generate_weld_image(
    defect_class: str,
    rng: np.random.Generator,
) -> tuple[bytes, Optional[list[int]]]:
    """Draw a robotic MIG steel fillet weld bead with ripple texture and optional porosity/spatter."""
    img = Image.new("RGB", (IMG_W, IMG_H), (52, 58, 66))
    draw = ImageDraw.Draw(img)

    # Brushed steel plate background with subtle grain
    for y in range(0, IMG_H, 2):
        shade = 52 + int(rng.integers(-6, 7))
        draw.line([(0, y), (IMG_W, y)], fill=(shade, shade + 4, shade + 10), width=2)

    seam_y = IMG_H // 2 + int(rng.integers(-24, 25))
    # Heat-affected zone (HAZ) subtle bluish-straw band around seam
    for dy in range(-58, 59):
        dist = abs(dy)
        if dist > 26:
            fade = max(0.0, 1.0 - (dist - 26) / 34.0)
            c = (
                int(58 + 26 * fade),
                int(60 + 18 * fade),
                int(68 + 28 * fade),
            )
            draw.line([(0, seam_y + dy), (IMG_W, seam_y + dy)], fill=c, width=1)

    # Weld bead ripples along the seam
    bead_h = 26
    for x in range(28, IMG_W - 28, 14):
        jitter_y = int(rng.integers(-2, 3))
        b_col = int(rng.integers(148, 178))
        draw.ellipse(
            [x - 16, seam_y - bead_h + jitter_y, x + 16, seam_y + bead_h + jitter_y],
            fill=(b_col, b_col + 2, b_col + 6),
            outline=(102, 108, 116),
            width=2,
        )
        # Specular ridge on each ripple
        draw.arc(
            [x - 12, seam_y - bead_h + 4 + jitter_y, x + 12, seam_y + bead_h - 4 + jitter_y],
            start=290,
            end=70,
            fill=(212, 218, 226),
            width=2,
        )

    gt_bbox_norm: Optional[list[int]] = None

    if defect_class == "POROSITY_GAS_LOSS":
        # Clustered dark surface pits/wormholes along a random section of the bead
        cluster_x = int(rng.integers(160, IMG_W - 180))
        n_pits = int(rng.integers(6, 12))
        xs, ys = [], []
        for _ in range(n_pits):
            px = cluster_x + int(rng.integers(-48, 49))
            py = seam_y + int(rng.integers(-14, 15))
            r = int(rng.integers(4, 9))
            draw.ellipse([px - r - 1, py - r - 1, px + r + 1, py + r + 1], fill=(72, 74, 80))
            draw.ellipse([px - r, py - r, px + r, py + r], fill=(14, 16, 20))
            xs.extend([px - r, px + r])
            ys.extend([py - r, py + r])
        ymin = max(0, int((min(ys) - 16) * 1000 / IMG_H))
        xmin = max(0, int((min(xs) - 16) * 1000 / IMG_W))
        ymax = min(1000, int((max(ys) + 16) * 1000 / IMG_H))
        xmax = min(1000, int((max(xs) + 16) * 1000 / IMG_W))
        gt_bbox_norm = [ymin, xmin, ymax, xmax]

    elif defect_class == "SPATTER_COSMETIC":
        # Hard negative: small metallic spatter balls BESIDE the bead (seam itself is sound)
        for _ in range(int(rng.integers(10, 18))):
            sx = int(rng.integers(60, IMG_W - 60))
            side = int(rng.choice([-1, 1]))
            sy = seam_y + side * int(rng.integers(44, 135))
            r = int(rng.integers(2, 5))
            draw.ellipse([sx - r, sy - r, sx + r, sy + r], fill=(182, 188, 198), outline=(92, 96, 104))

    img = _add_lighting_and_sensor_noise(img, rng)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), gt_bbox_norm


def generate_cnc_part_image(
    rng: np.random.Generator,
) -> tuple[bytes, Optional[list[int]]]:
    """Draw a machined CNC bore/housing surface (NO visible bearing defect — bearing is internal)."""
    img = Image.new("RGB", (IMG_W, IMG_H), (76, 82, 90))
    draw = ImageDraw.Draw(img)

    cx = IMG_W // 2 + int(rng.integers(-20, 21))
    cy = IMG_H // 2 + int(rng.integers(-16, 17))

    # Concentric machined metal face & bore
    for r in range(240, 62, -4):
        shade = 108 + int(16 * math.sin(r * 0.22)) + int(rng.integers(-4, 5))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(shade, shade + 2, shade + 6), width=3)

    # Inner bore shadow
    draw.ellipse([cx - 64, cy - 64, cx + 64, cy + 64], fill=(24, 28, 34), outline=(142, 148, 158), width=4)
    # Bolt-hole circle on flange
    for k in range(6):
        ang = math.radians(k * 60 + float(rng.uniform(-5, 5)))
        bx = int(cx + 165 * math.cos(ang))
        by = int(cy + 165 * math.sin(ang))
        draw.ellipse([bx - 16, by - 16, bx + 16, by + 16], fill=(32, 36, 42), outline=(156, 162, 172), width=2)

    img = _add_lighting_and_sensor_noise(img, rng)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), None
