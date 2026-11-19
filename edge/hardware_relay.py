"""
edge/hardware_relay.py
HardwareRelayController for USB Serial Andon Tower & Day-30 2-Wire Dry-Contact Relay:
- Supports real USB serial relay commands via `pyserial` (`RELAY_SERIAL_PORT`) with
  automatic mock serial fallback when hardware is disconnected.
- Supports switchable operating modes:
    * Mode 1 (`DAY1_ANDON_ONLY`): Drives Andon LED tower (GREEN / YELLOW / RED) with
      zero invasive PLC wiring. `ext_feed_hold_engaged` remains strictly False.
    * Mode 2 (`DAY30_EXT_FEED_HOLD_CUTOUT`): Drives Andon LEDs AND closes the 2-wire
      dry-contact relay into the CNC `EXT_FEED_HOLD` terminal block on YELLOW/RED faults.
"""
import logging
import time
from typing import Literal, Optional
from config.settings import settings

try:
    import serial  # type: ignore
except ImportError:
    serial = None

logger = logging.getLogger("vinyas_ai.edge.hardware_relay")

AndonState = Literal[
    "GREEN_NOMINAL",
    "GREEN_FALSE_POSITIVE_REJECTED",
    "YELLOW_M01_HOLD",
    "RED_PREEMPT",
]

RelayOperatingMode = Literal["DAY1_ANDON_ONLY", "DAY30_EXT_FEED_HOLD_CUTOUT"]

# Standard 4-channel USB Relay ASCII/byte command map (LCUS / CH340 compatible)
SERIAL_RELAY_COMMANDS: dict[str, bytes] = {
    "GREEN_NOMINAL": b"RELAY:GREEN=1,YELLOW=0,RED=0,FEEDHOLD=0\n",
    "GREEN_FALSE_POSITIVE_REJECTED": b"RELAY:GREEN=1,YELLOW=0,RED=0,FEEDHOLD=0\n",
    "YELLOW_M01_HOLD_ANDON": b"RELAY:GREEN=0,YELLOW=1,RED=0,FEEDHOLD=0\n",
    "YELLOW_M01_HOLD_CUTOUT": b"RELAY:GREEN=0,YELLOW=1,RED=0,FEEDHOLD=1\n",
    "RED_PREEMPT_ANDON": b"RELAY:GREEN=0,YELLOW=0,RED=1,FEEDHOLD=0\n",
    "RED_PREEMPT_CUTOUT": b"RELAY:GREEN=0,YELLOW=0,RED=1,FEEDHOLD=1\n",
}


class HardwareRelayController:
    def __init__(
        self,
        device_port: Optional[str] = None,
        baud_rate: int = 9600,
        operating_mode: Optional[RelayOperatingMode] = None,
    ):
        self.device_port = device_port if device_port is not None else settings.RELAY_SERIAL_PORT
        self.baud_rate = baud_rate
        self.operating_mode: RelayOperatingMode = operating_mode or settings.RELAY_OPERATING_MODE
        self.current_state: AndonState = "GREEN_NOMINAL"
        self.ext_feed_hold_engaged: bool = False
        self.hardware_connected: bool = False
        self.last_transition_epoch: float = time.time()
        self.last_serial_command: bytes = b""
        self.transition_history: list[dict] = []
        self._serial_conn = None

        self._try_connect_serial()

    def _try_connect_serial(self) -> None:
        if not self.device_port or serial is None:
            self.hardware_connected = False
            return
        try:
            self._serial_conn = serial.Serial(self.device_port, self.baud_rate, timeout=0.2)
            self.hardware_connected = True
            logger.info("Connected to USB serial relay at %s (%d baud)", self.device_port, self.baud_rate)
        except Exception as exc:
            self.hardware_connected = False
            self._serial_conn = None
            logger.warning("USB relay at %s unavailable (%s); using mock relay driver.", self.device_port, exc)

    def set_operating_mode(self, mode: RelayOperatingMode) -> RelayOperatingMode:
        self.operating_mode = mode
        settings.RELAY_OPERATING_MODE = mode
        if mode == "DAY1_ANDON_ONLY":
            self.ext_feed_hold_engaged = False
        logger.info("Relay operating mode set to %s", mode)
        return self.operating_mode

    def toggle_operating_mode(self) -> RelayOperatingMode:
        next_mode: RelayOperatingMode = (
            "DAY30_EXT_FEED_HOLD_CUTOUT"
            if self.operating_mode == "DAY1_ANDON_ONLY"
            else "DAY1_ANDON_ONLY"
        )
        return self.set_operating_mode(next_mode)

    def _dispatch_serial(self, cmd: bytes) -> None:
        self.last_serial_command = cmd
        if self._serial_conn is not None and self.hardware_connected:
            try:
                self._serial_conn.write(cmd)
                self._serial_conn.flush()
            except Exception as exc:
                logger.warning("Serial write failed (%s); falling back to mock relay log.", exc)
                self.hardware_connected = False

    def _set_state(self, state: AndonState) -> None:
        now = time.time()
        self.current_state = state
        self.last_transition_epoch = now

        cutout_active = (
            self.operating_mode == "DAY30_EXT_FEED_HOLD_CUTOUT"
            and state in ("YELLOW_M01_HOLD", "RED_PREEMPT")
        )
        self.ext_feed_hold_engaged = cutout_active

        if state in ("GREEN_NOMINAL", "GREEN_FALSE_POSITIVE_REJECTED"):
            cmd = SERIAL_RELAY_COMMANDS[state]
        elif state == "YELLOW_M01_HOLD":
            cmd = (
                SERIAL_RELAY_COMMANDS["YELLOW_M01_HOLD_CUTOUT"]
                if cutout_active
                else SERIAL_RELAY_COMMANDS["YELLOW_M01_HOLD_ANDON"]
            )
        else:
            cmd = (
                SERIAL_RELAY_COMMANDS["RED_PREEMPT_CUTOUT"]
                if cutout_active
                else SERIAL_RELAY_COMMANDS["RED_PREEMPT_ANDON"]
            )

        self._dispatch_serial(cmd)
        self.transition_history.append(
            {
                "state": state,
                "mode": self.operating_mode,
                "ext_feed_hold_engaged": self.ext_feed_hold_engaged,
                "serial_cmd": cmd.decode("ascii").strip(),
                "timestamp": now,
            }
        )
        if len(self.transition_history) > 128:
            self.transition_history.pop(0)

    def trigger_green_nominal(self) -> None:
        self._set_state("GREEN_NOMINAL")

    def trigger_yellow_m01_hold(self) -> None:
        self._set_state("YELLOW_M01_HOLD")

    def trigger_red_preempt(self) -> None:
        self._set_state("RED_PREEMPT")

    def close(self) -> None:
        if self._serial_conn is not None:
            try:
                self._serial_conn.close()
            except Exception:
                pass
            self._serial_conn = None
            self.hardware_connected = False


# Backwards-compatible alias
HardwareRelay = HardwareRelayController
