"""Physics-based 48 kHz CNC spindle vibration synthesis for Mock Rig v2.

Representative 7014C-class angular-contact bearing geometry (assumptions in docs/ASSUMPTIONS.md):
  n = 20 balls, d = 11.1 mm, D = 90.0 mm, contact angle alpha = 15 deg
  Shaft speed = 5400 rpm -> f_r = 90.0 Hz
  BPFO = (n / 2) * f_r * (1 - (d / D) * cos(alpha)) ~= 792.8 Hz
  BPFI = (n / 2) * f_r * (1 + (d / D) * cos(alpha)) ~= 1007.2 Hz
"""

from __future__ import annotations

import io
import math
import wave
from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, sosfilt


FS_HZ = 48_000
DURATION_SEC = 1.0
N_SAMPLES = int(FS_HZ * DURATION_SEC)

# Representative 7014C-class bearing geometry (documented in docs/ASSUMPTIONS.md)
BEARING_BALLS_N = 20
BALL_DIAM_MM = 11.1
PITCH_DIAM_MM = 90.0
CONTACT_ANGLE_DEG = 15.0
DEFAULT_RPM = 5400

_SOS_ISO_VEL = butter(4, [10.0, 1000.0], btype="bandpass", fs=FS_HZ, output="sos")


def compute_bearing_frequencies(
    rpm: float = DEFAULT_RPM,
    n_balls: int = BEARING_BALLS_N,
    ball_diam_mm: float = BALL_DIAM_MM,
    pitch_diam_mm: float = PITCH_DIAM_MM,
    contact_angle_deg: float = CONTACT_ANGLE_DEG,
) -> dict[str, float]:
    """Compute shaft frequency, BPFO, and BPFI from bearing geometry and shaft speed."""
    f_r = rpm / 60.0
    ratio = (ball_diam_mm / pitch_diam_mm) * math.cos(math.radians(contact_angle_deg))
    bpfo = 0.5 * n_balls * f_r * (1.0 - ratio)
    bpfi = 0.5 * n_balls * f_r * (1.0 + ratio)
    return {
        "shaft_hz": round(f_r, 3),
        "bpfo_hz": round(bpfo, 3),
        "bpfi_hz": round(bpfi, 3),
    }


@dataclass
class VibrationSample:
    signal_float32: np.ndarray
    wav_bytes: bytes
    rms_velocity_mms: float
    spindle_temp_c: float
    rpm: int
    bpfo_hz: float
    bpfi_hz: float


def _encode_wav_16bit(signal: np.ndarray, fs: int = FS_HZ) -> bytes:
    peak = float(np.max(np.abs(signal)))
    scale = 0.9 / max(peak, 1.0)
    pcm16 = np.clip(signal * scale * 32767.0, -32768.0, 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(fs)
        wf.writeframes(pcm16.tobytes())
    return buf.getvalue()


def generate_cnc_vibration(
    defect_class: str,
    severity: str,
    rng: np.random.Generator,
) -> VibrationSample:
    """Synthesize a 1.0 s 48 kHz vibration waveform and consistent telemetry."""
    rpm = int(DEFAULT_RPM + rng.integers(-35, 36))
    freqs = compute_bearing_frequencies(rpm=rpm)
    f_r = freqs["shaft_hz"]
    bpfo = freqs["bpfo_hz"]
    bpfi = freqs["bpfi_hz"]

    t = np.arange(N_SAMPLES, dtype=np.float64) / FS_HZ

    # Baseline nominal signal (calibrated in mm/s velocity equivalent for 10-1000 Hz + high-freq carrier)
    amp_1x = float(rng.uniform(0.55, 1.05))
    amp_2x = float(rng.uniform(0.18, 0.40))
    phase_1 = float(rng.uniform(0, 2 * np.pi))
    phase_2 = float(rng.uniform(0, 2 * np.pi))

    sig = (
        amp_1x * np.sin(2.0 * np.pi * f_r * t + phase_1)
        + amp_2x * np.sin(2.0 * np.pi * 2.0 * f_r * t + phase_2)
        + rng.normal(0.0, float(rng.uniform(0.28, 0.45)), size=N_SAMPLES)
    )

    # Mild cutting load modulation
    load_mod = 1.0 + 0.08 * np.sin(2.0 * np.pi * float(rng.uniform(4.0, 11.0)) * t)
    sig *= load_mod

    spindle_temp = float(rng.uniform(37.5, 44.0))

    if defect_class == "OUTER_RACE_FAULT":
        # Impulse train at BPFO (+/- 1% slip jitter) exciting ~4200 Hz structural resonance
        f_res = float(rng.uniform(4050.0, 4350.0))
        tau = float(rng.uniform(0.0008, 0.0012))  # ~1 ms decay
        imp_amp = float(rng.uniform(4.2, 6.2)) if severity == "severe" else float(rng.uniform(2.6, 3.8))
        # Also add low-frequency vibration energy consistent with severe/mild bearing wear
        extra_lf = float(rng.uniform(3.2, 4.8)) if severity == "severe" else float(rng.uniform(1.8, 2.9))
        sig += extra_lf * np.sin(2.0 * np.pi * bpfo * t + float(rng.uniform(0, 2 * np.pi))) * 0.45
        sig += extra_lf * np.sin(2.0 * np.pi * f_r * t + phase_1) * 0.55

        period = 1.0 / bpfo
        cur_t = float(rng.uniform(0.0, period))
        imp_len = int(0.006 * FS_HZ)
        local_t = np.arange(imp_len, dtype=np.float64) / FS_HZ
        kernel = np.exp(-local_t / tau) * np.sin(2.0 * np.pi * f_res * local_t)

        while cur_t < DURATION_SEC:
            idx = int(cur_t * FS_HZ)
            end = min(N_SAMPLES, idx + imp_len)
            if end > idx:
                jitter_amp = imp_amp * float(rng.uniform(0.85, 1.15))
                sig[idx:end] += jitter_amp * kernel[: end - idx]
            cur_t += period * float(rng.uniform(0.99, 1.01))

        spindle_temp = (
            float(rng.uniform(58.0, 66.5)) if severity == "severe" else float(rng.uniform(50.5, 57.5))
        )

    elif defect_class == "WRENCH_STRIKE":
        # Hard negative: single non-periodic external impact -> high kurtosis, no BPFO periodicity
        f_res = float(rng.uniform(2900.0, 3400.0))
        tau = 0.0032
        strike_t = float(rng.uniform(0.25, 0.75))
        idx = int(strike_t * FS_HZ)
        imp_len = int(0.025 * FS_HZ)
        local_t = np.arange(imp_len, dtype=np.float64) / FS_HZ
        kernel = 14.0 * np.exp(-local_t / tau) * np.sin(2.0 * np.pi * f_res * local_t)
        end = min(N_SAMPLES, idx + imp_len)
        sig[idx:end] += kernel[: end - idx]
        spindle_temp = float(rng.uniform(38.0, 44.5))

    elif defect_class == "IMBALANCE":
        # Elevated 1x shaft harmonic (ISO 20816-3 Zone C), no BPFO periodicity
        imbalance_amp = float(rng.uniform(4.2, 5.4))
        sig += imbalance_amp * np.sin(2.0 * np.pi * f_r * t + phase_1)
        spindle_temp = float(rng.uniform(45.0, 51.0))

    # Compute RMS velocity directly from the 10-1000 Hz filtered signal
    vel_band = sosfilt(_SOS_ISO_VEL, sig)
    rms_vel = float(np.sqrt(np.mean(vel_band[2400:] ** 2)))

    sig_f32 = sig.astype(np.float32)
    wav_bytes = _encode_wav_16bit(sig_f32, fs=FS_HZ)

    return VibrationSample(
        signal_float32=sig_f32,
        wav_bytes=wav_bytes,
        rms_velocity_mms=round(rms_vel, 2),
        spindle_temp_c=round(spindle_temp, 1),
        rpm=rpm,
        bpfo_hz=bpfo,
        bpfi_hz=bpfi,
    )
