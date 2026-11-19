"""
scripts/simulate_rig_stream.py
Replays 48 kHz stereo WAV stems into the Vinyas AI Stage A DSP pipeline.
Allows offline testing and stage live demo when physical USB rig is unplugged.
"""
import argparse
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from edge.hardware_relay import HardwareRelay
from edge.sensor_daemon import StereoSensorDaemon


def main():
    parser = argparse.ArgumentParser(description="Vinyas AI V2.1 Benchtop Rig Stream Simulator")
    parser.add_argument(
        "--fault",
        choices=["nominal", "wrench", "chatter", "overload"],
        default="chatter",
        help="Type of synthetic fault stem to stream",
    )
    parser.add_argument(
        "--loops",
        type=int,
        default=1,
        help="Number of times to loop the 2-second stem (0 for continuous)",
    )
    args = parser.parse_args()

    stem_map = {
        "nominal": "data/synthetic_faults/nominal_cut_48k.wav",
        "wrench": "data/synthetic_faults/wrench_strike_48k.wav",
        "chatter": "data/synthetic_faults/chatter_4210hz_48k.wav",
        "overload": "data/synthetic_faults/spindle_overload_48k.wav",
    }

    wav_path = PROJECT_ROOT / stem_map[args.fault]
    relay = HardwareRelay()

    def print_result(res: dict):
        state = res.get("stage_a_state")
        latency = res.get("latency_ms", 0.0)
        coherence = res.get("coherence", 0.0)
        ae_rms = res.get("ae_rms_g", 0.0)
        ct_ripple = res.get("ct_ripple_std_amps", 0.0)
        print(
            f"[{time.strftime('%X')}] State: {state:<28} | Latency: {latency:.2f} ms | "
            f"Coh: {coherence:.2f} | AE: {ae_rms:.2f} G | CT: {ct_ripple:.2f} A"
        )

    daemon = StereoSensorDaemon(hardware_relay=relay, callback=print_result)
    print(f"Streaming {wav_path.name} through Vinyas AI Stage A DSP...")
    daemon.run_replay_loop(wav_path, loop_count=args.loops)
    print("Stream finished. Final relay state:", relay.current_state)


if __name__ == "__main__":
    main()
