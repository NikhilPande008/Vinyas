"""Tier-1A deterministic DSP & process-window gate (`backend/dsp/envelope.py`).

Self-contained NumPy/SciPy implementation:
- CNC: 48 kHz bandpass (2-8 kHz 4th-order Butterworth SOS) -> |hilbert| envelope ->
  DC removal -> FFT -> BPFO (+/-3%) & 2x BPFO SNR in dB vs 50-2000 Hz median floor,
  kurtosis, and ISO 20816-3 Group 2 rigid-support reference velocity zone.
- PCB: SAC305 reflow process-window checks.
- WELD: MIG shielding gas flow and arc voltage checks.
- Generates a clean envelope-spectrum PNG (axis labels only, zero verdict/answer text).
"""

from __future__ import annotations

import base64
import io
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image, ImageDraw
from scipy.signal import butter, hilbert, sosfilt

from backend.mock_rig.vibration import FS_HZ, compute_bearing_frequencies
from backend.schemas import SensorTelemetry


_SOS_RESONANCE_BAND = butter(4, [2000.0, 8000.0], btype="bandpass", fs=FS_HZ, output="sos")


@dataclass
class T1AResult:
    line: str
    escalating_flags: list[str] = field(default_factory=list)
    info_flags: list[str] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)
    summary: str = "Nominal"
    latency_ms: int = 0
    envelope_png_bytes: Optional[bytes] = None
    envelope_data_url: Optional[str] = None

    @property
    def any_escalating_flag(self) -> bool:
        return len(self.escalating_flags) > 0

    @property
    def all_flags(self) -> list[str]:
        return list(self.escalating_flags) + list(self.info_flags)


def _iso_20816_3_zone(rms_mms: float) -> str:
    """ISO 20816-3 Group 2 rigid-support reference velocity zones (mm/s RMS)."""
    if rms_mms < 1.4:
        return "A"
    if rms_mms < 2.8:
        return "B"
    if rms_mms < 4.5:
        return "C"
    return "D"


def _load_wav_float32(wav_path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(wav_path), "rb") as wf:
        fs = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if wf.getnchannels() > 1:
            pcm = pcm.reshape(-1, wf.getnchannels())[:, 0]
    return pcm, fs


def _render_envelope_spectrum_png(
    freqs: np.ndarray,
    mag: np.ndarray,
    bpfo_hz: float,
) -> bytes:
    """Render a 640x260 envelope spectrum PNG (0-2000 Hz) with neutral axis labels only."""
    w, h = 640, 260
    pad_l, pad_r, pad_t, pad_b = 54, 18, 22, 34
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    img = Image.new("RGB", (w, h), (15, 23, 42))
    draw = ImageDraw.Draw(img)

    # Grid & axes
    draw.rectangle([pad_l, pad_t, w - pad_r, h - pad_b], outline=(71, 85, 105), width=1)
    max_freq = 2000.0
    mask = (freqs >= 20.0) & (freqs <= max_freq)
    f_sub = freqs[mask]
    m_sub = mag[mask]
    if len(m_sub) == 0:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    # Convert to dB relative to median floor
    med = float(np.median(m_sub)) + 1e-12
    db = 20.0 * np.log10((m_sub + 1e-12) / med)
    db_min, db_max = -6.0, max(24.0, float(np.max(db)) + 2.0)

    # Horizontal grid lines (dB)
    for db_tick in (0, 6, 12, 18, 24):
        if db_min <= db_tick <= db_max:
            y = int(pad_t + plot_h * (1.0 - (db_tick - db_min) / (db_max - db_min)))
            draw.line([(pad_l, y), (w - pad_r, y)], fill=(30, 41, 59), width=1)
            draw.text((8, y - 6), f"{db_tick:+d}dB", fill=(148, 163, 184))

    # Vertical grid lines (Hz)
    for hz_tick in (0, 500, 1000, 1500, 2000):
        x = int(pad_l + plot_w * (hz_tick / max_freq))
        draw.line([(x, pad_t), (x, h - pad_b)], fill=(30, 41, 59), width=1)
        label_x = min(x - 14, w - 46)
        draw.text((label_x, h - pad_b + 8), f"{hz_tick}Hz", fill=(148, 163, 184))

    # Dashed reference markers at computed BPFO and 2x BPFO (geometry-derived, not a verdict)
    for mult, col in ((1, (251, 191, 36)), (2, (245, 158, 11))):
        target_hz = bpfo_hz * mult
        if target_hz <= max_freq:
            x = int(pad_l + plot_w * (target_hz / max_freq))
            for y_seg in range(pad_t, h - pad_b, 8):
                draw.line([(x, y_seg), (x, min(h - pad_b, y_seg + 4))], fill=col, width=1)
            draw.text((x + 3, pad_t + 3), f"{mult}xBPFO", fill=col)

    # Downsample curve to pixel columns
    pts: list[tuple[int, int]] = []
    for col_px in range(plot_w):
        f0 = (col_px / plot_w) * max_freq
        f1 = ((col_px + 1) / plot_w) * max_freq
        sel = (f_sub >= f0) & (f_sub < f1)
        if np.any(sel):
            val = float(np.max(db[sel]))
            y = int(pad_t + plot_h * (1.0 - (val - db_min) / (db_max - db_min)))
            y = max(pad_t, min(h - pad_b, y))
            pts.append((pad_l + col_px, y))
    if len(pts) >= 2:
        draw.line(pts, fill=(56, 189, 248), width=2)

    draw.text((pad_l + 6, 4), "Hilbert Envelope Spectrum (2-8 kHz bandpass)", fill=(203, 213, 225))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def analyze_cnc_vibration_envelope(
    signal: np.ndarray,
    fs: int,
    rpm: int,
    rms_velocity_mms: float,
) -> tuple[dict[str, Any], list[str], list[str], bytes]:
    """Run Hilbert envelope FFT and ISO 20816-3 reference zone check on CNC vibration."""
    sos = _SOS_RESONANCE_BAND if fs == FS_HZ else butter(4, [2000.0, 8000.0], btype="bandpass", fs=fs, output="sos")
    bp = sosfilt(sos, signal.astype(np.float64))
    # Strip 20 ms startup transient
    strip = min(int(0.02 * fs), len(bp) // 10)
    bp = bp[strip:]

    # Kurtosis on bandpassed signal (detects sharp transient impacts like wrench strike)
    bp_zero = bp - np.mean(bp)
    var = float(np.mean(bp_zero ** 2)) + 1e-18
    kurtosis = float(np.mean(bp_zero ** 4) / (var ** 2))

    # Hilbert envelope -> remove mean -> Hann window -> rFFT
    env = np.abs(hilbert(bp))
    env = env - np.mean(env)
    win = np.hanning(len(env))
    spec = np.abs(np.fft.rfft(env * win))
    freqs = np.fft.rfftfreq(len(env), d=1.0 / fs)

    # Median noise floor in 50-2000 Hz
    floor_mask = (freqs >= 50.0) & (freqs <= 2000.0)
    med_floor = float(np.median(spec[floor_mask])) + 1e-12

    bearing = compute_bearing_frequencies(rpm=rpm or 5400)
    bpfo = bearing["bpfo_hz"]

    def _peak_snr_db(target_hz: float, tol_frac: float = 0.03) -> tuple[float, float]:
        band = (freqs >= target_hz * (1.0 - tol_frac)) & (freqs <= target_hz * (1.0 + tol_frac))
        if not np.any(band):
            return 0.0, target_hz
        idx = int(np.argmax(spec[band]))
        peak_val = float(spec[band][idx])
        peak_hz = float(freqs[band][idx])
        snr_db = float(20.0 * np.log10((peak_val + 1e-12) / med_floor))
        return round(snr_db, 2), round(peak_hz, 1)

    bpfo_snr_db, bpfo_peak_hz = _peak_snr_db(bpfo, tol_frac=0.03)
    bpfo_2x_snr_db, bpfo_2x_peak_hz = _peak_snr_db(2.0 * bpfo, tol_frac=0.03)
    iso_zone = _iso_20816_3_zone(rms_velocity_mms)

    escalating: list[str] = []
    info: list[str] = []

    # Amplitude dB (20*log10 vs median noise floor): Rayleigh noise max over +/-3% band is ~10.5 dB,
    # while true periodic BPFO impacts exceed 14 dB at 1x BPFO and 11 dB at 2x BPFO.
    if bpfo_snr_db >= 14.0 and bpfo_2x_snr_db >= 11.0:
        escalating.append("BEARING_PERIODIC_IMPACT")
    if iso_zone in ("C", "D"):
        escalating.append("VIBRATION_ZONE_C_OR_D")
    if kurtosis >= 8.0 and "BEARING_PERIODIC_IMPACT" not in escalating:
        # Informational only: rejects non-periodic single impacts (e.g., wrench strike)
        info.append("TRANSIENT_IMPACT")

    png_bytes = _render_envelope_spectrum_png(freqs, spec, bpfo)

    features = {
        "rpm": rpm,
        "shaft_hz": bearing["shaft_hz"],
        "bpfo_expected_hz": bpfo,
        "bpfo_peak_hz": bpfo_peak_hz,
        "bpfo_snr_db": bpfo_snr_db,
        "bpfo_2x_peak_hz": bpfo_2x_peak_hz,
        "bpfo_2x_snr_db": bpfo_2x_snr_db,
        "bandpass_kurtosis": round(kurtosis, 2),
        "rms_velocity_mms": round(rms_velocity_mms, 2),
        "iso_20816_3_zone": iso_zone,
    }
    return features, escalating, info, png_bytes


def evaluate_t1a_signal_gate(
    line: str,
    telemetry: SensorTelemetry,
    wav_path: Optional[Path] = None,
) -> T1AResult:
    """Run deterministic Tier-1A DSP / process-window checks for PCB, CNC, or WELD."""
    t0 = time.perf_counter()
    line_u = line.upper()
    escalating: list[str] = []
    info: list[str] = []
    features: dict[str, Any] = {}
    env_png: Optional[bytes] = None
    env_url: Optional[str] = None

    if line_u == "CNC":
        if wav_path is not None and wav_path.is_file():
            sig, fs = _load_wav_float32(wav_path)
            features, escalating, info, env_png = analyze_cnc_vibration_envelope(
                signal=sig,
                fs=fs,
                rpm=telemetry.line_speed_rpm or 5400,
                rms_velocity_mms=telemetry.vibration_rms_mms,
            )
            env_url = "data:image/png;base64," + base64.b64encode(env_png).decode("ascii")
        else:
            zone = _iso_20816_3_zone(telemetry.vibration_rms_mms)
            features = {
                "rms_velocity_mms": telemetry.vibration_rms_mms,
                "iso_20816_3_zone": zone,
                "wav_present": False,
            }
            if zone in ("C", "D"):
                escalating.append("VIBRATION_ZONE_C_OR_D")

    elif line_u == "PCB":
        ramp = telemetry.reflow_ramp_c_per_s
        peak = telemetry.reflow_peak_c if telemetry.reflow_peak_c is not None else telemetry.temperature_c
        tal = telemetry.reflow_tal_s
        features = {
            "reflow_ramp_c_per_s": ramp,
            "reflow_peak_c": peak,
            "reflow_tal_s": tal,
        }
        if ramp is not None and (ramp < 1.0 or ramp > 3.0):
            escalating.append("REFLOW_RAMP_OUT_OF_WINDOW")
        if peak is not None and (peak < 235.0 or peak > 250.0):
            escalating.append("REFLOW_PEAK_OUT_OF_WINDOW")
        if tal is not None and (tal < 45.0 or tal > 90.0):
            escalating.append("REFLOW_TAL_OUT_OF_WINDOW")

    elif line_u == "WELD":
        gas = telemetry.shielding_gas_lpm
        arc_v = telemetry.arc_voltage_v
        features = {
            "shielding_gas_lpm": gas,
            "arc_voltage_v": arc_v,
            "wire_feed_m_per_min": telemetry.wire_feed_m_per_min,
        }
        if gas is not None and gas < 12.0:
            escalating.append("SHIELDING_GAS_LOW")
        if arc_v is not None and (arc_v < 19.0 or arc_v > 24.5):
            escalating.append("ARC_VOLTAGE_OUT_OF_WINDOW")

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if escalating:
        summary = f"Flagged: {', '.join(escalating)}"
    elif info:
        summary = f"Nominal (info: {', '.join(info)})"
    else:
        summary = "Nominal"

    return T1AResult(
        line=line_u,
        escalating_flags=escalating,
        info_flags=info,
        features=features,
        summary=summary,
        latency_ms=elapsed_ms,
        envelope_png_bytes=env_png,
        envelope_data_url=env_url,
    )
