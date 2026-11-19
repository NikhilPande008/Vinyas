"""
edge/sensor_daemon.py
Hardware-Synchronized Stereo 48 kHz USB Audio Capture Daemon:
- Channels: Left (Ch0) = Contact Piezo Vibration, Right (Ch1) = Single-Conductor Split-Core CT.
- Captures real-time (12000, 2) 250ms rolling stereo windows at 48,000 Hz via `sounddevice`
  (or `pyaudio` fallback) when `HARDWARE_SOURCE == "USB_STEREO_ADC"`.
- Seamlessly falls back to WAV stem replay (`data/synthetic_faults/`) if the USB audio
  interface is unplugged or `HARDWARE_SOURCE == "WAV_REPLAY"`.
"""
import logging
import multiprocessing as mp
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Literal, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
from scipy.io import wavfile
from config.settings import settings
from edge.hardware_relay import HardwareRelayController
from edge.hilbert_envelope_dsp import stage_a_deterministic_fast_path

try:
    import sounddevice as sd  # type: ignore
except ImportError:
    sd = None

try:
    import pyaudio  # type: ignore
except ImportError:
    pyaudio = None

logger = logging.getLogger("vinyas_ai.edge.sensor_daemon")


def list_stereo_audio_input_devices(sample_rate: int = 48000) -> list[dict]:
    """Discovers connected audio input devices supporting >=2 channels at sample_rate."""
    devices: list[dict] = []
    if sd is not None:
        try:
            for idx, dev in enumerate(sd.query_devices()):
                max_in = int(dev.get("max_input_channels", 0))
                if max_in >= 2:
                    stereo_ok = True
                    try:
                        sd.check_input_settings(device=idx, channels=2, samplerate=sample_rate)
                    except Exception:
                        stereo_ok = False
                    devices.append(
                        {
                            "index": idx,
                            "name": dev.get("name", f"Device {idx}"),
                            "max_input_channels": max_in,
                            "default_samplerate": float(dev.get("default_samplerate", 0)),
                            "supports_48k_stereo": stereo_ok,
                        }
                    )
        except Exception as exc:
            logger.warning("sounddevice query_devices failed: %s", exc)
    return devices


class StereoSensorDaemon:
    def __init__(
        self,
        hardware_relay: Optional[HardwareRelayController] = None,
        gemma_triage_queue: Optional[mp.Queue] = None,
        callback: Optional[Callable[[dict], None]] = None,
        chunk_samples: int = 12000,  # 250 ms at 48 kHz
        hardware_source: Optional[Literal["USB_STEREO_ADC", "WAV_REPLAY"]] = None,
        audio_device_index: Optional[int] = None,
    ):
        self.hardware_relay = hardware_relay or HardwareRelayController()
        self.gemma_triage_queue = gemma_triage_queue or mp.Queue()
        self.callback = callback
        self.chunk_samples = chunk_samples
        self.sample_rate = settings.SAMPLE_RATE_HZ
        self.hardware_source = hardware_source or settings.HARDWARE_SOURCE
        self.audio_device_index = (
            audio_device_index if audio_device_index is not None else settings.AUDIO_DEVICE_INDEX
        )
        self.active_source_label: Literal["LIVE_USB", "SIMULATED"] = "SIMULATED"
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self.latest_result: dict = {
            "stage_a_state": "GREEN_NOMINAL",
            "latency_ms": 0.0,
            "coherence": 0.0,
            "ae_rms_g": 0.0,
            "ct_ripple_std_amps": 0.0,
        }
        self.active_machine_context: dict = {
            "cycle_id": "CYC_CHAKAN_04_99281",
            "machine_id": "FANUC_0iTF_CHAKAN_04",
            "work_order_id": "WO_ALSI9CU3_DIFF_882",
            "tool_id": "T03",
            "pass_type": "FINISHING",
        }

    def process_window(self, stereo_window: np.ndarray) -> dict:
        """Processes a single (12000, 2) stereo chunk through Stage A."""
        if stereo_window.shape != (self.chunk_samples, 2):
            raise ValueError(f"Expected shape ({self.chunk_samples}, 2), got {stereo_window.shape}")

        res = stage_a_deterministic_fast_path(
            stereo_chunk_250ms=stereo_window,
            hardware_relay=self.hardware_relay,
            gemma_triage_queue=self.gemma_triage_queue,
            machine_context=self.active_machine_context,
        )
        res["source"] = self.active_source_label
        self.latest_result = res
        if self.callback:
            self.callback(res)
        return res

    def capture_live_window(self) -> Optional[np.ndarray]:
        """Captures a single (12000, 2) 250ms stereo window from USB ADC via sounddevice or pyaudio."""
        if sd is not None:
            try:
                rec = sd.rec(
                    self.chunk_samples,
                    samplerate=self.sample_rate,
                    channels=2,
                    dtype="float32",
                    device=self.audio_device_index,
                )
                sd.wait()
                self.active_source_label = "LIVE_USB"
                return np.asarray(rec, dtype=np.float32)
            except Exception as exc:
                logger.warning("sounddevice capture failed (%s)", exc)

        if pyaudio is not None:
            pa = None
            stream = None
            try:
                pa = pyaudio.PyAudio()
                stream = pa.open(
                    format=pyaudio.paFloat32,
                    channels=2,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=self.audio_device_index,
                    frames_per_buffer=self.chunk_samples,
                )
                raw = stream.read(self.chunk_samples, exception_on_overflow=False)
                arr = np.frombuffer(raw, dtype=np.float32).reshape((self.chunk_samples, 2))
                self.active_source_label = "LIVE_USB"
                return arr
            except Exception as exc:
                logger.warning("pyaudio capture failed (%s)", exc)
            finally:
                if stream is not None:
                    stream.stop_stream()
                    stream.close()
                if pa is not None:
                    pa.terminate()
        return None

    def run_live_usb_loop(
        self,
        max_windows: int = 0,
        fallback_wav_path: Optional[Path] = None,
    ) -> None:
        """
        Streams real-time 250ms (12000, 2) rolling windows from USB Stereo ADC via sounddevice.
        Automatically falls back to WAV replay if hardware is disconnected.
        """
        if self.hardware_source != "USB_STEREO_ADC" or (sd is None and pyaudio is None):
            target_wav = fallback_wav_path or (settings.SYNTHETIC_FAULTS_DIR / "chatter_4210hz_48k.wav")
            logger.info("Using WAV replay source (%s)", target_wav.name)
            self.run_replay_loop(target_wav, loop_count=1)
            return

        self.is_running = True
        windows_read = 0
        try:
            if sd is not None:
                with sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=2,
                    dtype="float32",
                    blocksize=self.chunk_samples,
                    device=self.audio_device_index,
                ) as stream:
                    self.active_source_label = "LIVE_USB"
                    logger.info("Live 48 kHz USB Stereo ADC stream started (device=%s)", self.audio_device_index)
                    while self.is_running and (max_windows == 0 or windows_read < max_windows):
                        data, _overflowed = stream.read(self.chunk_samples)
                        self.process_window(np.asarray(data, dtype=np.float32))
                        windows_read += 1
                    return
        except Exception as exc:
            logger.warning("USB Stereo ADC unplugged or unavailable (%s); falling back to WAV replay.", exc)

        self.is_running = False
        target_wav = fallback_wav_path or (settings.SYNTHETIC_FAULTS_DIR / "chatter_4210hz_48k.wav")
        self.run_replay_loop(target_wav, loop_count=1)

    def run_replay_loop(self, wav_path: Path, loop_count: int = 1) -> None:
        """Streams a pre-recorded or synthetic 48kHz stereo WAV file."""
        if not wav_path.exists():
            raise FileNotFoundError(f"Replay WAV not found: {wav_path}")

        fs, data = wavfile.read(wav_path)
        if fs != self.sample_rate or data.ndim != 2 or data.shape[1] != 2:
            raise ValueError(f"WAV must be 48kHz stereo, got fs={fs}, shape={data.shape}")

        if data.dtype == np.int16:
            data = (data / 32768.0).astype(np.float32)
        elif data.dtype != np.float32:
            data = data.astype(np.float32)

        self.active_source_label = "SIMULATED"
        self.is_running = True
        logger.info("Starting WAV replay of %s (%d samples)", wav_path.name, len(data))

        iteration = 0
        while self.is_running and (loop_count == 0 or iteration < loop_count):
            iteration += 1
            idx = 0
            while self.is_running and (idx + self.chunk_samples <= len(data)):
                chunk = data[idx : idx + self.chunk_samples, :]
                self.process_window(chunk)
                idx += self.chunk_samples
                time.sleep(0.01)

        self.is_running = False

    def start_background(self, wav_path: Optional[Path] = None, loop_count: int = 1) -> None:
        if self.hardware_source == "USB_STEREO_ADC":
            self._thread = threading.Thread(
                target=self.run_live_usb_loop,
                kwargs={"fallback_wav_path": wav_path},
                daemon=True,
            )
        else:
            target = wav_path or (settings.SYNTHETIC_FAULTS_DIR / "chatter_4210hz_48k.wav")
            self._thread = threading.Thread(
                target=self.run_replay_loop,
                args=(target, loop_count),
                daemon=True,
            )
        self._thread.start()

    def start_replay_background(self, wav_path: Path, loop_count: int = 1) -> None:
        self._thread = threading.Thread(
            target=self.run_replay_loop,
            args=(wav_path, loop_count),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
