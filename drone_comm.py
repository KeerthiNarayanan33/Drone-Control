"""
Drone Communication Core Layer for RC FPV Protocol
Reverse engineered from com.cooingdv.rcfpv (base.apk)

Strictly adheres to:
- UDP target: 192.168.1.1:7099
- Keep-Alive Heartbeat: [0x01, 0x01] at 1 Hz
- Flight Control Packet: 9-byte packet at 20 Hz (50 ms):
    [0x03, 0x66, Roll, Pitch, Thr, Yaw, Flags, Checksum, 0x99]
- Checksum: Roll ^ Pitch ^ Thr ^ Yaw ^ Flags
- Disengage: [0x08, 0x01]
- Safety Watchdog: automatic neutral fallback when control input ceases
"""

import socket
import threading
import time
import logging
from typing import Callable, Optional, Dict, Any, Tuple

# Protocol Constants
DEFAULT_DRONE_IP = "192.168.1.1"
DEFAULT_CONTROL_PORT = 7099
DEFAULT_RTSP_PORT = 7070
RTSP_URL = f"rtsp://{DEFAULT_DRONE_IP}:{DEFAULT_RTSP_PORT}/webcam"

MAGIC_BYTE_PREFIX = 0x03
MAGIC_BYTE_START = 0x66  # 102 decimal
MAGIC_BYTE_END = 0x99    # 153 decimal (-103 signed)

NEUTRAL_STICK_VALUE = 128  # 0x80
STICK_MIN = 1
STICK_MAX = 255

# Control Flags (Byte 6 / byte5) Bitmask
FLAG_FAST_FLY        = 0x01  # Bit 0: High speed mode
FLAG_FAST_DROP       = 0x02  # Bit 1: Auto land / fast descend
FLAG_EMERGENCY_STOP  = 0x04  # Bit 2: Immediate rotor cutoff
FLAG_CIRCLE_TURN_END = 0x08  # Bit 3: 360 flip
FLAG_NO_HEAD_MODE    = 0x10  # Bit 4: Headless mode
FLAG_UNLOCK_TAKEOFF  = 0x20  # Bit 5: Motor arm / auto takeoff
FLAG_GYRO_CALIBRATE  = 0x80  # Bit 7: Gyroscope calibration

# Keep-alive heartbeat payload
HEARTBEAT_PAYLOAD = bytes([0x01, 0x01])

# Controller disengage payload
DISENGAGE_PAYLOAD = bytes([0x08, 0x01])

# Event Acknowledgments (SD card / hardware buttons)
ACK_PHOTO = bytes([0x09, 0x01])
ACK_VIDEO = bytes([0x09, 0x02])


class DroneControllerCore:
    """Manages UDP socket connection, packet construction, thread timing, and safety watchdog."""

    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        control_port: int = DEFAULT_CONTROL_PORT,
        log_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None
    ):
        self.drone_ip = drone_ip
        self.control_port = control_port
        self.log_callback = log_callback

        # Sockets & Networking
        self._socket: Optional[socket.socket] = None
        self._is_running = False
        self._is_connected = False

        # Flight State Variables (1 - 255, neutral 128)
        self.roll = NEUTRAL_STICK_VALUE
        self.pitch = NEUTRAL_STICK_VALUE
        self.throttle = NEUTRAL_STICK_VALUE
        self.yaw = NEUTRAL_STICK_VALUE
        self.flags = 0

        # Safety & Limits Settings (Application-Level Limits)
        self.speed_limit_pct = 100.0        # Application limit: 20% - 100%
        self.dead_zone = 12                 # Stick dead zone around 128
        self.yaw_hardware_deadband = True   # Hardware deadband [104, 152] -> 128
        self.watchdog_timeout_sec = 0.3     # Auto-neutral if no command for 300ms
        self.last_input_time = time.time()
        self.auto_neutral_enabled = True

        # Telemetry & Diagnostics
        self.packets_sent_count = 0
        self.packets_recv_count = 0
        self.heartbeats_sent_count = 0
        self.last_sent_hex = ""
        self.last_recv_hex = ""
        self.last_recv_time = 0.0
        self.camera_resolution_id = 0
        self.camera_index = 0

        # Threading
        self._lock = threading.Lock()
        self._send_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._recv_thread: Optional[threading.Thread] = None

    def _log(self, level: str, message: str, meta: Optional[Dict[str, Any]] = None):
        if self.log_callback:
            try:
                self.log_callback(level, message, meta or {})
            except Exception:
                pass

    @staticmethod
    def calculate_checksum(roll: int, pitch: int, throttle: int, yaw: int, flags: int) -> int:
        """Checksum formula reverse-engineered from FlyControlTask: Roll ^ Pitch ^ Thr ^ Yaw ^ Flags."""
        return (roll ^ pitch ^ throttle ^ yaw ^ (flags & 0xFF)) & 0xFF

    def build_flight_packet(self, roll: int, pitch: int, throttle: int, yaw: int, flags: int) -> bytes:
        """Constructs the canonical 9-byte UDP packet for drone flight control."""
        # Enforce hard clamping to [1, 255]
        r = max(STICK_MIN, min(STICK_MAX, int(roll)))
        p = max(STICK_MIN, min(STICK_MAX, int(pitch)))
        t = max(0, min(STICK_MAX, int(throttle)))  # Throttle can be 0 for motor cutoff
        y = max(STICK_MIN, min(STICK_MAX, int(yaw)))
        f = flags & 0xFF

        checksum = self.calculate_checksum(r, p, t, y, f)
        packet = bytes([
            MAGIC_BYTE_PREFIX,
            MAGIC_BYTE_START,
            r,
            p,
            t,
            y,
            f,
            checksum,
            MAGIC_BYTE_END
        ])
        return packet

    def _apply_safety_limits(self, raw_roll: int, raw_pitch: int, raw_throttle: int, raw_yaw: int) -> Tuple[int, int, int, int]:
        """Applies dead zones, application-level speed ceiling scaling, and stick clamping."""
        def apply_axis(val: int) -> int:
            delta = val - NEUTRAL_STICK_VALUE
            if abs(delta) <= self.dead_zone:
                return NEUTRAL_STICK_VALUE
            # Scale delta by speed limit percentage
            scaled_delta = delta * (self.speed_limit_pct / 100.0)
            scaled_val = int(NEUTRAL_STICK_VALUE + scaled_delta)
            return max(STICK_MIN, min(STICK_MAX, scaled_val))

        r = apply_axis(raw_roll)
        p = apply_axis(raw_pitch)
        t = apply_axis(raw_throttle)
        y = apply_axis(raw_yaw)

        # Apply confirmed firmware deadband for yaw: [104, 152] -> 128
        if self.yaw_hardware_deadband:
            if 104 <= y <= 152:
                y = NEUTRAL_STICK_VALUE

        return r, p, t, y

    def connect(self) -> bool:
        """Initializes the UDP socket and launches the heartbeat, send, and receive worker loops."""
        with self._lock:
            if self._is_running:
                return True

            try:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._socket.settimeout(0.5)
                # Allow broadcast or local testing
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

                self._is_running = True
                self._is_connected = True
                self.last_input_time = time.time()

                # Start Heartbeat loop (1 Hz)
                self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="DroneHeartbeat")
                self._heartbeat_thread.start()

                # Start Command Send loop (20 Hz / 50ms)
                self._send_thread = threading.Thread(target=self._send_loop, daemon=True, name="DroneCommandStream")
                self._send_thread.start()

                # Start Receive loop
                self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True, name="DroneReceiver")
                self._recv_thread.start()

                self._log("INFO", f"Connected UDP socket to {self.drone_ip}:{self.control_port}")
                return True
            except Exception as e:
                self._log("ERROR", f"Failed to initialize socket: {e}")
                self._is_running = False
                self._is_connected = False
                if self._socket:
                    try:
                        self._socket.close()
                    except Exception:
                        pass
                    self._socket = None
                return False

    def disconnect(self):
        """Sends the disengage packet and cleanly terminates all networking threads."""
        self._log("INFO", "Disconnecting from drone...")
        with self._lock:
            self._is_running = False
            self._is_connected = False

            # Send controller disengage packet [0x08, 0x01]
            if self._socket:
                try:
                    self._socket.sendto(DISENGAGE_PAYLOAD, (self.drone_ip, self.control_port))
                except Exception:
                    pass

        # Wait briefly for threads to wind down
        time.sleep(0.1)

        with self._lock:
            if self._socket:
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None

        self._log("INFO", "Drone disconnected and socket closed.")

    def set_sticks(self, roll: int, pitch: int, throttle: int, yaw: int):
        """Updates stick input values. Values are expected in the 1-255 range (128 neutral)."""
        with self._lock:
            self.roll = roll
            self.pitch = pitch
            self.throttle = throttle
            self.yaw = yaw
            self.last_input_time = time.time()

    def set_flags(self, flags: int):
        """Sets control flags bitmask (Takeoff, Land, Emergency Stop, etc.)."""
        with self._lock:
            self.flags = flags
            self.last_input_time = time.time()

    def trigger_takeoff(self):
        """Triggers the arm & auto-takeoff command (Bit 5 / 0x20)."""
        self._log("ACTION", "Command: TAKEOFF triggered")
        with self._lock:
            self.flags |= FLAG_UNLOCK_TAKEOFF
            self.last_input_time = time.time()

    def trigger_land(self):
        """Triggers the auto-land / fast drop command (Bit 1 / 0x02)."""
        self._log("ACTION", "Command: LAND triggered")
        with self._lock:
            self.flags |= FLAG_FAST_DROP
            self.last_input_time = time.time()

    def trigger_emergency_stop(self):
        """Triggers immediate rotor cutoff (Bit 2 / 0x04)."""
        self._log("EMERGENCY", "EMERGENCY STOP TRIGGERED!")
        with self._lock:
            self.flags = FLAG_EMERGENCY_STOP
            self.throttle = 0  # Zero out throttle
            self.roll = NEUTRAL_STICK_VALUE
            self.pitch = NEUTRAL_STICK_VALUE
            self.yaw = NEUTRAL_STICK_VALUE
            self.last_input_time = time.time()

    def trigger_gyro_calibration(self):
        """Triggers gyroscope/accelerometer calibration (Bit 7 / 0x80)."""
        self._log("ACTION", "Command: GYRO CALIBRATION triggered")
        with self._lock:
            self.flags |= FLAG_GYRO_CALIBRATE
            self.last_input_time = time.time()

    def switch_camera(self):
        """Sends camera switch command [0x06, 0x01] or [0x06, 0x02]."""
        with self._lock:
            self.camera_index = 2 if self.camera_index == 1 else 1
            cmd = bytes([0x06, self.camera_index])
            if self._socket:
                try:
                    self._socket.sendto(cmd, (self.drone_ip, self.control_port))
                    self._log("ACTION", f"Camera switch sent: {cmd.hex()}")
                except Exception as e:
                    self._log("ERROR", f"Camera switch error: {e}")

    def _heartbeat_loop(self):
        """Sends keep-alive packet [0x01, 0x01] every 1000 ms."""
        while self._is_running:
            try:
                if self._socket:
                    self._socket.sendto(HEARTBEAT_PAYLOAD, (self.drone_ip, self.control_port))
                    self.heartbeats_sent_count += 1
            except Exception as e:
                self._log("WARNING", f"Heartbeat send failed: {e}")
            time.sleep(1.0)

    def _send_loop(self):
        """Sends 9-byte flight control packet at 20 Hz (50 ms interval)."""
        while self._is_running:
            start_time = time.time()

            with self._lock:
                now = time.time()
                # Watchdog check: if no new input for watchdog_timeout_sec, revert to neutral
                if self.auto_neutral_enabled and (now - self.last_input_time > self.watchdog_timeout_sec):
                    self.roll = NEUTRAL_STICK_VALUE
                    self.pitch = NEUTRAL_STICK_VALUE
                    self.throttle = NEUTRAL_STICK_VALUE
                    self.yaw = NEUTRAL_STICK_VALUE
                    # Clear transient action flags after execution
                    self.flags &= ~(FLAG_UNLOCK_TAKEOFF | FLAG_FAST_DROP | FLAG_GYRO_CALIBRATE)

                # Apply safety limits (speed ceiling, dead-zone)
                safe_r, safe_p, safe_t, safe_y = self._apply_safety_limits(
                    self.roll, self.pitch, self.throttle, self.yaw
                )

                packet = self.build_flight_packet(safe_r, safe_p, safe_t, safe_y, self.flags)
                self.last_sent_hex = packet.hex().upper()

            if self._socket:
                try:
                    self._socket.sendto(packet, (self.drone_ip, self.control_port))
                    self.packets_sent_count += 1
                except Exception as e:
                    self._log("ERROR", f"Send flight packet failed: {e}")

            # Sleep remaining time to maintain 50 ms (20 Hz) loop
            elapsed = time.time() - start_time
            sleep_time = max(0.005, 0.050 - elapsed)
            time.sleep(sleep_time)

    def _recv_loop(self):
        """Listens for inbound telemetry / ACK packets on UDP 7099."""
        while self._is_running:
            try:
                if not self._socket:
                    time.sleep(0.1)
                    continue

                data, addr = self._socket.recvfrom(1024)
                if data:
                    self.packets_recv_count += 1
                    self.last_recv_hex = data.hex().upper()
                    self.last_recv_time = time.time()
                    self._process_inbound_packet(data)
            except socket.timeout:
                continue
            except Exception as e:
                if self._is_running:
                    self._log("DEBUG", f"Recv loop note: {e}")
                time.sleep(0.05)

    def _process_inbound_packet(self, data: bytes):
        """Parses resolution byte and hardware button event codes ('M' / 'X')."""
        if len(data) >= 1:
            self.camera_resolution_id = data[0]

        # Check for hardware photo/video triggers
        if len(data) > 4:
            event_char = data[2]
            if event_char == 77:  # 'M' (0x4D) - photo event
                self._log("EVENT", "Drone hardware photo button pressed. Sending ACK.")
                try:
                    if self._socket:
                        self._socket.sendto(ACK_PHOTO, (self.drone_ip, self.control_port))
                except Exception:
                    pass
            elif event_char == 88:  # 'X' (0x58) - video event
                self._log("EVENT", "Drone hardware video button pressed. Sending ACK.")
                try:
                    if self._socket:
                        self._socket.sendto(ACK_VIDEO, (self.drone_ip, self.control_port))
                except Exception:
                    pass

    def get_status(self) -> Dict[str, Any]:
        """Returns the current controller status and diagnostic snapshot."""
        now = time.time()
        time_since_recv = (now - self.last_recv_time) if self.last_recv_time > 0 else -1.0
        return {
            "connected": self._is_connected,
            "drone_ip": self.drone_ip,
            "control_port": self.control_port,
            "rtsp_url": RTSP_URL,
            "packets_sent": self.packets_sent_count,
            "packets_recv": self.packets_recv_count,
            "heartbeats_sent": self.heartbeats_sent_count,
            "last_sent_hex": self.last_sent_hex,
            "last_recv_hex": self.last_recv_hex,
            "time_since_recv_sec": round(time_since_recv, 2) if time_since_recv >= 0 else None,
            "sticks": {
                "roll": self.roll,
                "pitch": self.pitch,
                "throttle": self.throttle,
                "yaw": self.yaw,
                "flags": self.flags
            },
            "settings": {
                "speed_limit_pct": self.speed_limit_pct,
                "dead_zone": self.dead_zone,
                "watchdog_timeout_sec": self.watchdog_timeout_sec
            },
            # Real telemetry provided by drone:
            "camera_resolution_id": self.camera_resolution_id,
            # Unsupported telemetry clearly flagged as N/A:
            "telemetry": {
                "battery": "N/A",
                "altitude": "N/A",
                "gps": "N/A",
                "satellites": "N/A",
                "speed_mps": "N/A"
            }
        }
