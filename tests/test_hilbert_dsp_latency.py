"""
tests/test_hilbert_dsp_latency.py
Unit tests verifying Vinyas Tier 2 Edge DSP & Hardware Relay Controller:
1. Sub-1.4 ms (and <2.0 ms) execution speed on (12000, 2) 250ms rolling window.
2. Wrench-strike false-positive rejection (brief impulse on Ch 0 + flat Ch 1 -> GREEN_FALSE_POSITIVE_REJECTED).
3. Light finishing chatter protection (sustained 4,210 Hz vibration on Ch 0 with low CT ripple <0.12 A
   MUST NOT be vetoed -> triggers YELLOW_M01_HOLD via primary Ch 0 vibration detector).
4. Regenerative chatter with CT coupling triggers YELLOW_M01_HOLD with coherence >= 0.72 & anti-aliased
   16 kHz polyphase resampling (`resample_poly`).
5. Catastrophic overload trips RED_PREEMPT.
6. HardwareRelayController Mode 1 (`DAY1_ANDON_ONLY`) vs Mode 2 (`DAY30_EXT_FEED_HOLD_CUTOUT`).
"""
import multiprocessing as mp
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from edge.hardware_relay import HardwareRelayController
from edge.hilbert_envelope_dsp import (
    stage_a_deterministic_fast_path,
    downsample_to_16khz,
)

FAULTS_DIR = Path("data/synthetic_faults")


def test_stage_a_latency_under_1_4_ms():
    relay = HardwareRelayController()
    queue = mp.Queue()
    dummy_window = np.random.normal(0, 0.05, (12000, 2)).astype(np.float32)

    stage_a_deterministic_fast_path(dummy_window, relay, queue, {})

    latencies = []
    for _ in range(10):
        res = stage_a_deterministic_fast_path(dummy_window, relay, queue, {})
        latencies.append(res["latency_ms"])

    avg_latency = float(np.mean(latencies))
    min_latency = float(np.min(latencies))
    assert min_latency < 1.4, f"Minimum latency {min_latency} ms exceeded 1.4 ms threshold"
    assert avg_latency < 2.0, f"Average latency {avg_latency} ms exceeded 2.0 ms bound"


def test_wrench_strike_false_positive_rejection():
    relay = HardwareRelayController()
    queue = mp.Queue()
    fs, data = wavfile.read(FAULTS_DIR / "wrench_strike_48k.wav")
    assert fs == 48000

    strike_chunk = data[24000:36000, :]
    res = stage_a_deterministic_fast_path(strike_chunk, relay, queue, {})

    assert res["stage_a_state"] == "GREEN_FALSE_POSITIVE_REJECTED"
    assert res["coherence"] == 0.0
    assert res["ct_ripple_std_amps"] < 0.12
    assert relay.current_state != "RED_PREEMPT"


def test_light_finishing_cut_chatter_not_vetoed_by_low_ct_ripple():
    """Sustained 4,210 Hz vibration on Ch 0 with tiny CT ripple (<0.12 A) MUST trigger YELLOW_M01_HOLD."""
    relay = HardwareRelayController()
    queue = mp.Queue()
    t = np.arange(12000, dtype=np.float32) / 48000.0
    # Sustained 4,210 Hz finishing chatter (~0.6 G RMS), flat tiny CT (~0.03 A)
    ch0_vib = 0.08 * np.sin(2.0 * np.pi * 4210.0 * t) + np.random.normal(0, 0.005, 12000).astype(np.float32)
    ch1_ct = 0.002 * np.sin(2.0 * np.pi * 50.0 * t)
    light_cut_chunk = np.column_stack([ch0_vib, ch1_ct]).astype(np.float32)

    res = stage_a_deterministic_fast_path(light_cut_chunk, relay, queue, {"tool_id": "T03", "pass_type": "FINISHING"})
    assert res["ct_ripple_std_amps"] < 0.12
    assert res["stage_a_state"] == "YELLOW_M01_HOLD"
    assert res["detection_source"] == "PRIMARY_CH0_LIGHT_FINISHING"
    assert res["band_power_ratio_2k_8k"] >= 0.45
    assert res["spectral_crest_factor"] >= 5.0
    assert relay.current_state == "YELLOW_M01_HOLD"


def test_regenerative_chatter_triggers_yellow_m01_hold():
    relay = HardwareRelayController()
    queue = mp.Queue()
    fs, data = wavfile.read(FAULTS_DIR / "chatter_4210hz_48k.wav")
    assert fs == 48000

    chunk = data[12000:24000, :]
    res = stage_a_deterministic_fast_path(chunk, relay, queue, {"tool_id": "T03", "pass_type": "FINISHING"})

    assert res["stage_a_state"] == "YELLOW_M01_HOLD"
    assert res["coherence"] >= 0.72
    assert relay.current_state == "YELLOW_M01_HOLD"
    item = queue.get(timeout=0.5)
    assert item["peak_coherence"] >= 0.72
    # Verify anti-aliased 16 kHz polyphase resampling produced (4000, 2) float32 = 32,000 bytes
    downsampled = downsample_to_16khz(chunk)
    assert downsampled.shape == (4000, 2)
    assert len(item["stereo_pcm_16k"]) == 4000 * 2 * 4


def test_catastrophic_overload_trips_red_preempt():
    relay = HardwareRelayController()
    queue = mp.Queue()
    fs, data = wavfile.read(FAULTS_DIR / "spindle_overload_48k.wav")
    assert fs == 48000

    chunk = data[:12000, :]
    res = stage_a_deterministic_fast_path(chunk, relay, queue, {})

    assert res["stage_a_state"] == "RED_PREEMPT"
    assert relay.current_state == "RED_PREEMPT"


def test_hardware_relay_dual_mode_switching():
    relay = HardwareRelayController(operating_mode="DAY1_ANDON_ONLY")
    relay.trigger_yellow_m01_hold()
    assert relay.current_state == "YELLOW_M01_HOLD"
    assert relay.ext_feed_hold_engaged is False
    assert b"FEEDHOLD=0" in relay.last_serial_command

    relay.set_operating_mode("DAY30_EXT_FEED_HOLD_CUTOUT")
    relay.trigger_yellow_m01_hold()
    assert relay.ext_feed_hold_engaged is True
    assert b"FEEDHOLD=1" in relay.last_serial_command

    relay.trigger_green_nominal()
    assert relay.ext_feed_hold_engaged is False
    assert b"FEEDHOLD=0" in relay.last_serial_command
